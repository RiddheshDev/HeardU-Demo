from langchain_tavily import TavilySearch
from textwrap import dedent
from dotenv import load_dotenv
from langchain_chroma import Chroma
import openai 
from langchain_openai import OpenAIEmbeddings
from langchain.tools.retriever import create_retriever_tool
from typing import Optional
from langchain_core.runnables import RunnableConfig
from src.langgraph.func import db_conn 
# from src.langgraph.func import DataBaseToolGraph
import os
import datetime
import json

# def some_function():
#     from src.langgraph.graphs import DataBaseToolGraph

# some_function()

class Tools:
    def __init__(self):
        load_dotenv()
        os.environ['TAVILY_API_KEY'] = os.getenv("TAVILY_API_KEY")
        os.environ['PINECONE_API_KEY'] = os.getenv('PINECONE_API_KEY')
        self.tavily_search_tool = self.tavily_search()
        openai.api_key = os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")
        self.embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")  
        self.vector_tool = self.get_vector_db()

    # @staticmethod
    # def get_event_details():
    #     """This tools returns the Housing societies events details"""

    #     message = dedent(""" Society General Meeting - 15th April 2025, Community Hall, 5:00 PM - 7:00 PM, Monthly meeting to discuss society affairs, snacks provided.

    # Annual Residents' BBQ Party - 20th May 2025, Society Park, 4:00 PM - 9:00 PM, Annual BBQ for residents, music and games included.

    # Eid-ul-Fitr Celebration - 22nd April 2025, Community Hall, 6:00 PM - 9:00 PM, Eid prayers and community dinner, RSVP required.

    # Yoga and Wellness Session - 5th May 2025, Society Garden, 7:00 AM - 8:00 AM, Morning yoga session, free for all residents.

    # Diwali Festival Celebration - 12th November 2025, Society Courtyard, 6:30 PM - 10:00 PM, Diwali celebration with fireworks, traditional wear recommended.

    # Children’s Art & Craft Workshop - 30th June 2025, Kids Playroom, 10:00 AM - 12:00 PM, Creative art session for children, materials provided.

    # Society Annual Picnic - 10th July 2025, Green Meadows Park, 8:00 AM - 4:00 PM, Family picnic with outdoor activities, transport arranged.

    # Independence Day Celebration - 15th August 2025, Society Flagpole Area, 9:00 AM - 11:00 AM, Flag hoisting and cultural performances, refreshments served.

    # Halloween Party - 31st October 2025, Community Hall, 7:00 PM - 10:00 PM, Halloween party with costume competition, spooky treats welcome.

    # New Year’s Eve Countdown Party - 31st December 2025, Clubhouse, 9:00 PM - 1:00 AM, New Year's Eve celebration with music, formal attire.
    #     """)
    #     return message
    
        

    @staticmethod
    def tavily_search():
        "This tool"
        tavily_search_tool = TavilySearch(description="You are an websearch tool which can search anything as users requirement If the user asks a websearch related question then use tavily_search_tool to provide answers. Always use Goregoan as nearby location",
           max_results="3",topic='general',include_raw_content=False,search_depth='advanced')
        return tavily_search_tool

    def get_vector_db(self):
        vector_store = Chroma(collection_name='housing_agent',embedding_function=self.embeddings,persist_directory=r'Database\db')
        retrive = vector_store.as_retriever(search_kwargs={'k':2})
        retriever_tool = create_retriever_tool(retrive,'retrieve_issues_solution','Search & return questions to ask regarding any mentioned any complaint or issue by th user')
        return retriever_tool
    
    @staticmethod
    async def coupons(config:RunnableConfig):
        """THIS TOOLS RETURNS A COUPON CODE."""
        print((30)*'=','config',config,(30)*'=',flush=True)
        user_id = config['metadata'].get('user_id')
        client_id = config['metadata'].get('client_id')

        # conn = await db_conn()
        async with db_conn() as conn:
            # 1. Check for active coupon already assigned
            active_coupon = await conn.fetchrow("""
                SELECT *
                FROM rewards.user_coupons
                WHERE user_id = $1 AND client_id = $2
                    AND status = 'active' AND expires_at >= NOW()
                LIMIT 1
            """, user_id, client_id)

            if active_coupon:
                coupon_output = active_coupon.get('coupon_description')
                return {'coupon':coupon_output}

            # 2. Fetch a valid coupon for user level and brand
            coupon = await conn.fetchrow("""
                SELECT *
                FROM rewards.coupons
                WHERE client_id = $1
                    AND is_active = TRUE
                    AND start_date <= NOW()
                    AND end_date >= NOW()
                    AND (usage_limit IS NULL OR (
                        (SELECT COUNT(*) FROM rewards.user_coupons WHERE coupon_id = rewards.coupons.coupon_id) < usage_limit)
                    )
                    AND (usage_limit_per_user IS NULL OR (
                        (SELECT COUNT(*) FROM rewards.user_coupons WHERE user_id = $2 AND coupon_id = rewards.coupons.coupon_id) < usage_limit_per_user)
                    ) order by start_date asc
                LIMIT 1
            """, client_id, user_id)

            if not coupon:
                return {"message": "No available coupon found for and brand."}

            # 3. Compute expiry
            assigned_at = datetime.datetime.now()
            expires_at = None

            validity_days = coupon.get('validity_days')
            end_date = coupon.get("end_date")

            if validity_days:
                expires_at = assigned_at + datetime.timedelta(days=validity_days)
            else:
                expires_at = end_date

            if end_date:
                expires_at = min(expires_at, end_date)

            # 4. Snapshot coupon info
            coupon_snapshot = {
                    "code": coupon["code"],
                    "description": coupon["description"],
                    "discount_type": coupon["discount_type"],
                    "discount_value": float(coupon["discount_value"]),
                    "min_order_value": float(coupon["min_order_value"]) if coupon["min_order_value"] else None,
                    "max_discount_value": float(coupon["max_discount_value"]) if coupon["max_discount_value"] else None,
                    "start_date": coupon["start_date"].isoformat(),
                    "end_date": expires_at.isoformat(),
                    "coupon_img": coupon['coupon_img']
                }

            # 5. Insert into user_coupons
            await conn.execute("""
                INSERT INTO rewards.user_coupons (
                    user_id, coupon_id, client_id, status, assigned_at, expires_at, coupon_description
                ) VALUES ($1, $2, $3, 'active', $4, $5, $6)
            """, user_id, coupon["coupon_id"], client_id, assigned_at, expires_at, json.dumps(coupon_snapshot))

            await conn.close()
            return {"coupon": coupon_snapshot}
        
    @staticmethod
    def products(user_input : Optional[str],config : RunnableConfig):
        """This tool returns products from sql database"""
        print('user input : ', user_input)
        client_id = config['metadata']['client_id']
        tool_graph_builder = DataBaseToolGraph(config = config)
        tool_graph_compiled = tool_graph_builder.compile_graph()
        response = tool_graph_compiled.invoke({"messages": [user_input],'user_input':user_input,'client_id':client_id})
        return {"products": response['products']}
    
    @staticmethod
    async def get_event_details(user_input:Optional[str],config: RunnableConfig):
        """This tool returns events/meetings info from sql database"""
        print('user input : ', user_input)
        client_id = config['metadata']['client_id']
        tool_graph_builder = DataBaseToolGraph(config = config)
        tool_graph_compiled = tool_graph_builder.compile_graph()
        response = await tool_graph_compiled.ainvoke({"messages": [user_input],'user_input':user_input,'client_id':client_id})
        return {"events": response['events']}

class DataBaseToolGraph:
    def __init__(self,config):
        self.config = config
        self.semantic_activate = self.semantic_search_activate()

    def db_tool_graph_builder(self):
        from src.langgraph import nodes 
        from src.langgraph.states import ToolState
        from langgraph.graph import  StateGraph, START, END #type: ignore
        
        tool_nodes = nodes.db_search(config=self.config)
        self.tool_graph = StateGraph(ToolState)
        self.tool_graph.add_node("sql_agent", tool_nodes.sql_agent)
        if self.semantic_activate:
            self.tool_graph.add_node("semantic_agent", tool_nodes.semantic_agent)
        self.tool_graph.add_node("output_validator", tool_nodes.output_validator())

        self.tool_graph.add_edge(START,"sql_agent")
        if self.semantic_activate:            
            self.tool_graph.add_edge(START,"semantic_agent")
            self.tool_graph.add_edge('semantic_agent','output_validator') 
        self.tool_graph.add_edge('sql_agent','output_validator') 
        self.tool_graph.add_edge("output_validator", END) 

    def compile_graph(self,memory = None):
        self.db_tool_graph_builder()
        return self.tool_graph.compile(checkpointer=memory)
    
    def semantic_search_activate(self):
        type = self.config['metadata'].get('use_case','')
        type = type.split('_')[0]
        if type in ['b2c']:
            return True
        else :
            return False

            

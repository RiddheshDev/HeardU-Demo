import os
from textwrap import dedent
from langgraph.prebuilt import tool_node # type: ignore  
from langchain_core.messages import ToolMessage ,AIMessage,HumanMessage
from langchain_core.prompts import PromptTemplate
import yaml
import sys
from src.langgraph.LLMs import CreateLLM
from langchain_core.output_parsers import JsonOutputParser
from src.langgraph.tools import Tools
from src.langgraph.states import *
from src.langgraph.func import *
from src.langgraph.analyze import *
from src.langgraph.utilits import PatchedSQLDatabase, retry_with_backoff, extract_last_tool_data
from src.langgraph.logger_config import logger 
import urllib.parse
import asyncpg
from typing import Optional
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError
import time
import json
from langchain_community.utilities import SQLDatabase  ##Langchain DB connection for sql_graph
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit ##Langchain DB connection for sql_graph
from langgraph.prebuilt import create_react_agent  # type: ignore 
import asyncio
from decimal import Decimal  ##for converting string into list in eval
import ast  ##for converting string into list 
import datetime  ##for converting string into list 
from pinecone import Pinecone ## For conecting Vector DB 

def load_yaml():
    with open(os.path.abspath('src/langgraph/prompts.yaml'),'r', encoding='utf-8') as file :
        data = yaml.safe_load(file)
    return data

def summarize_memory(state:MessagesState,ai_response):
    prompts = load_yaml().get('memory', {})
    llm = CreateLLM.openai_llm(model='gpt-4.1-mini-2025-04-14')
    summary = state.get('chat_summary',"")
    user_input = state['user_input']
    if summary:
        summary_prompt = prompts['summary_1']
    else :
        summary_prompt = prompts['summary_2']
    prompt = PromptTemplate(input_variables=['summary','user_input','ai_response'],template=summary_prompt)
    chain = prompt| llm| JsonOutputParser()
    user_input = state['user_input']
    ai_response = ai_response
    response = chain.invoke({'user_input': user_input, "ai_response": ai_response, "summary":summary})
    # print('Summariizng memory done :',response,flush=True)
    return {"chat_summary":response['summary']}  

def summarize_memory2(chat_history):
    prompts = load_yaml().get('memory', {})
    llm = CreateLLM.openai_llm(model='gpt-4.1-mini-2025-04-14')
    llm_structured = llm.with_structured_output(Memory)
    prompt = prompts['summary_3']
    prompt = PromptTemplate(input_variables=['chat_history'],template=prompt)
    chain = prompt| llm_structured
    response = chain.invoke({"chat_history":chat_history})
    # print('Summariizng memory done :',response,flush=True)
    return {"chat_summary":response.chat_summary}  

async def get_inactive_thread_ids():
    async def  _get_inactive_thread_ids():  
        conn = await asyncpg.connect(
            user=os.getenv('PSQL_USERNAME'),
            password=os.getenv('PSQL_PASSWORD'),
            database=os.getenv('PSQL_DATABASE'),
            host=os.getenv('PSQL_HOST')
        )
        query = """
        SELECT 
        json_build_object(
            'user_id', metadata->>'user_id',
            'use_case', metadata->>'use_case',
            'client_id', metadata->>'client_id'
        ) AS metadata_object,
        thread_id FROM sessions.checkpoints
        GROUP BY thread_id, metadata->>'user_id', metadata->>'use_case',metadata->>'client_id'
        HAVING EXTRACT(EPOCH FROM (NOW() - MAX(date_time))) >= 600
        ORDER BY MAX(date_time) DESC;
        """

        rows = await conn.fetch(query)
        thread_metadata_dict = {row['thread_id']: row['metadata_object'] for row in rows}  # Only extract thread_id from each row

        await conn.close()
        return thread_metadata_dict
    thread_metadata_dict = await retry_with_backoff(logger=logger,func= _get_inactive_thread_ids)
    return thread_metadata_dict
    
async def fetch_user_profile(user_id: str,client_id : str,config:RunnableConfig):
    try:
        user_logger = config['configurable'].get('logger')
        conn = await asyncpg.connect(user=os.getenv('PSQL_USERNAME'), password=os.getenv('PSQL_PASSWORD'), 
            database=os.getenv('PSQL_DATABASE'), host=os.getenv('PSQL_HOST'))
        # Fetch user profile
        async def _get_details():
            user_logger.info("Fetching required details")
            user_row = await conn.fetchrow(
                'SELECT name, age, gender, preferences, address FROM general_information.user_profile WHERE user_id = $1 and client_id = $2' 
                , user_id,client_id)
            if user_row:
                user_details = {"name": user_row["name"], "age": user_row["age"],
                    "gender": user_row["gender"],"preferences": user_row["preferences"], "address" : user_row['address']
                    }
                is_first_time_user = False
            else:
                user_details = {"name": None, "age": None, "gender": None, "preferences": None, "address": None
                }
                is_first_time_user = True

            # Fetch client details (optional if provided)
            if client_id:
                output_row = await conn.fetchrow(
                    'SELECT client, location, description, contact, specials FROM general_information.client_profile WHERE client_id = $1', 
                    client_id)
                
                if output_row:
                    client_details = {"name": output_row["client"], "location": output_row["location"],
                        "description": output_row["description"], "contact": output_row["contact"],"specials":output_row['specials']}
                else:
                    client_details = {"info": None}
            else:
                client_details = {"info": None}
            return user_details,is_first_time_user,client_details
        
        user_details, is_first_time_user, client_details = await retry_with_backoff(logger=logger, func=_get_details)

        async def _is_first_time_user():
            if not is_first_time_user :
            # Fetch user profile
                chat_summary = await conn.fetchrow(
                    'SELECT chat_summary FROM chats.user_chat_history WHERE user_id = $1 and ' \
                    'client_id = $2 order by date_time desc limit 1', user_id,client_id)
                if chat_summary is None:
                    chat_summary = {'chat_summary': 'None'}
            else:            
                chat_summary = {'chat_summary':'None'}
            return chat_summary
        chat_summary = await retry_with_backoff(logger=user_logger,func=_is_first_time_user)
        print(chat_summary,flush=True)
        await conn.close()
        user_logger.info('Details Fetched')
        print('\nUser Data fetched',user_details,flush=True)
        print('\nClient Details',client_details,flush=True)
        print('\nOld chat history',chat_summary.get('chat_summary',""),flush=True)
        # print('\nOld chat history',chat_summary,flush=True)
        return {
            "user_details": user_details,
            "first_time_user": is_first_time_user,
            "client_details": client_details,
            "old_chat_summary" : chat_summary.get('chat_summary',"") }   
    except Exception as e:
        user_logger.exception('Failed fetching required details',error=str(e))
        raise

async def ingate(prompts,llm,state: MessagesState, config: RunnableConfig) -> dict:
    try:
        user_logger = config['configurable'].get('logger')        
        user_input = state['user_input']
        chat_history = state.get('chat_history', '')[-8:]

        # Prepare LLM prompt
        prompt = PromptTemplate(
            input_variables=['user_input', 'chat_history'],
            template=prompts['ingate']
        )
        chain = prompt| llm.with_structured_output(InGate)

        # Start fetching user profile in parallel (only if needed)
        user_profile_task = None
        if not state.get("user_profile_loaded"):
            user_id = config["metadata"]["user_id"]
            client_id = config["metadata"]["client_id"]
            user_profile_task = asyncio.create_task(fetch_user_profile(user_id, client_id=client_id,config=config))

        # Await the LLM response
        # response = await chain.ainvoke({
        #     'user_input': user_input,
        #     'chat_history': chat_history
        # })
        user_logger.info("Getting response from ingate agent")
        response = await retry_with_backoff(user_logger,chain.invoke,input={'user_input': user_input,'chat_history': chat_history})
        # If invalid input, return early without waiting for profile
        if response.valid != 'yes':
            return {
                'ai_response': response.ai_response,
                'valid': response.valid
            }

        # If user profile was requested, await and return full data
        if user_profile_task:
            data = await user_profile_task
            return {
                "user_profile": data["user_details"],
                "user_profile_loaded": "yes",
                "first_time_user": data["first_time_user"],
                "client": data["client_details"],
                "old_chat_summary": data["old_chat_summary"],
                "valid": response.valid
            }

        # Else just return the validation status
        return {
            "valid": response.valid
        }
    except Exception as e:
        user_logger.exception(f'Error at Ingate - {config['metadata'].get('use_case')}',error=str(e))
        raise


class restaurant_feedback:
    def __init__(self,config):
        self.config = config
        self.prompts = load_yaml().get('restaurant_feedback','')
        tools = Tools()
        self.tools = [tools.coupons]
        self.llm =  CreateLLM.gemini_llm()
        self.agent_llm = CreateLLM.gemini_llm()
        # self.llm = CreateLLM.openai_llm(model='gpt-4.1-mini-2025-04-14')
        # self.agent_llm = CreateLLM.openai_llm()
        self.agent_llm_w_tool = self.agent_llm.bind_tools(self.tools)
        self.conninfo = db_conninfo()

    def ingate_node(self):
        async def _ingate_node(state:MessagesState,config:RunnableConfig):
            return await ingate(prompts=self.prompts,llm=self.llm,state=state,config=config)  
        return _ingate_node
    
    async def flow_agent(self,state:MessagesState,config:RunnableConfig):
        try:    
            chat_history = state.get('chat_history', '')[-8:]
            user_input = state.get('user_input')
            user_logger = config.get('configurable').get('logger')
            message = self.prompts['flow_agent']
            prompt = PromptTemplate(input_variables=['chat_history','user_input'],template=message)
            chain = prompt | self.llm | JsonOutputParser()
            # output = chain.invoke({'chat_history':chat_history,'user_input':user_input})
            output = await retry_with_backoff(user_logger,chain.invoke,input = {'chat_history':chat_history,'user_input':user_input})
            # print(output)
            return {'flow_type':output['output'].lower()}
        except Exception as e:
            user_logger.exception('Error occured in - Flow agent',error = str(e))
            raise    


    async def agent(self,state:MessagesState,config:RunnableConfig):
        try:
            ## Extract required variables
            user_input = state['user_input']
            user_details = state['user_profile']
            client_details = state['client']
            chat_history = state.get('chat_history',[])
            chat_history_w_tool = state.get('chat_history_w_tool',[]) 
            # chat_summary = state.get('chat_summary','None')
            old_chat_summary= state.get('old_chat_summary','')
            message = self.prompts['agent']
            user_logger = config['configurable'].get('logger')
            ## Loading LLM, Tool, Prompt and get response
            agent_llm_w_tool = self.agent_llm_w_tool
            #Append user input ONLY if tool wasn't already called
            prompt = PromptTemplate( input_variables=['user_input', 'chat_history', 'user_details', 'client_details', 'old_chat_summary', 'tool_output'],template=message)
            user_logger.info(f"Getting response from agent")
            chain = prompt | agent_llm_w_tool
            if not state.get('tool_called', False):
                # chain = prompt | agent_llm_tool
                # print("Prompt",prompt.format(user_input=user_input,chat_history=chat_history_w_tool,
                    # user_details=user_details,client_details=client_details,old_chat_summary=old_chat_summary,tool_output=None),flush=True)
                response = await retry_with_backoff(user_logger,chain.invoke,input={'user_input':user_input,'chat_history':chat_history_w_tool,
                    'user_details':user_details,'client_details':client_details,'old_chat_summary':old_chat_summary,'tool_output':None})
            else:
                # tool_output = chat_history_w_tool[-2:]  ## can be improved
                tool_output = extract_last_tool_data(chat_history_w_tool)
                
                # print("Prompt",prompt.format(user_input=user_input,chat_history=chat_history,
                    # user_details=user_details,client_details=client_details,old_chat_summary=old_chat_summary,tool_output=tool_output),flush=True)
                response = await retry_with_backoff(user_logger,chain.invoke,input={'user_input':user_input,'chat_history':chat_history,
                    'user_details':user_details,'client_details':client_details,'old_chat_summary':old_chat_summary,'tool_output':tool_output})

            if not state.get('tool_called', False):
                chat_history_w_tool.append({'role': 'user', 'content': user_input})
                chat_history.append({'role': 'user', 'content': user_input})
            # If tool is called, return tool_call info and stop here

            if hasattr(response, 'tool_calls') and response.tool_calls:
                print('Tool used',response.tool_calls[0].get('name'),flush=True)
                args = response.tool_calls[0].get('args')
                args = {k:v for k,v in args.items() if k != 'config'}
                chat_history_w_tool.append({'tool_call':response.tool_calls[0].get('name'),'args':args})
                return {"messages":[HumanMessage(content=user_input),response],'tool_output':response,'tool_name': response.tool_calls[0].get('name'),
                        'chat_history_w_tool':chat_history_w_tool,'chat_history':chat_history ,'tool_called':True}
            #If no tool is used, or second time after tool: add final AI response
            ai_msg = {'role':'ai','content':response.content}
            chat_history.append(ai_msg)
            chat_history_w_tool.append(ai_msg)
            # chat_summary = summarize_memory(state,ai_msg)
            return {'ai_response':response.content,'chat_history':chat_history,"messages":[HumanMessage(content=user_input),response],
                    'tool_called':False,'chat_history_w_tool':chat_history_w_tool}
        
        except Exception as e:
            user_logger.exception("Error occured in - Agent generating response",error = str(e))
            raise
        
    async def agent2(self,state:MessagesState,config:RunnableConfig):
        try:
            user_input = state['user_input']
            user_details = state['user_profile']
            client_details = state['client']
            chat_history = state.get('chat_history',[])
            old_chat_summary= state.get('old_chat_summary','')
            user_logger = config['configurable'].get('logger')
            
            message = self.prompts['agent2']
            prompt = PromptTemplate(input_variables=['client_details','user_details','old_chat_summary','chat_history','user_input'],template=message)
            chain = prompt | self.llm
            response = chain.invoke({'client_details':client_details,'user_details':user_details,'old_chat_summary':old_chat_summary,
                                    'chat_history':chat_history,'user_input':user_input})
            response = await retry_with_backoff(user_logger,chain.invoke,input = {'client_details':client_details,'user_details':user_details,'old_chat_summary':old_chat_summary,
                                    'chat_history':chat_history,'user_input':user_input})
            
            chat_history.append({'role': 'user', 'content': user_input})
            ai_msg = {'role':'ai','content':response.content}
            chat_history.append(ai_msg)
            return {'ai_response':response.content,'chat_history':chat_history,"messages":[HumanMessage(content=user_input),response]}
        except Exception as e :
            user_logger.exception('Error occured in - Agent generating response',error =str(e))
            raise

    async def tool_data_updated(self,state:MessagesState,config:RunnableConfig):
            try :   
                user_logger = config['configurable'].get('logger')          
                tool_name   = state.get('tool_name','') 
                tool_output = state.get('tool_output',[])
                tool_output = next((i for i in reversed(tool_output) if isinstance(i, ToolMessage)), ToolMessage(content="No relevant tool output", tool_call_id='dummy_id'))
                chat_history_w_tool = state.get('chat_history_w_tool',[])
                
                if tool_name == 'coupons':
                    response = json.loads(tool_output.content)
                    if "message" in response.keys():
                        chat_history_w_tool.append({'tool_output':tool_output.content})
                        return {'chat_history_w_tool':chat_history_w_tool,'tool_name':None} 
                    response = json.loads(response['coupon'])
                    output = {k:v for k,v in response.items() if k not in ['coupon_img']}
                    chat_history_w_tool.append({'tool_output':output})
                    return {'chat_history_w_tool':chat_history_w_tool,'coupon':response}
                    
                chat_history_w_tool.append({'tool_output':tool_output.content})
                return {'chat_history_w_tool':chat_history_w_tool}
            
            except Exception as e:
                user_logger.exception('Error occured in - tool_data_updated',error = str(e))
                raise

    async def conversation_end(self,state:MessagesState,config:RunnableConfig):
        try: 
            chat_history = state['chat_history'][-6:]
            user_input = state['user_input']
            ai_response = state['ai_response']
            message = self.prompts['end_conversation']
            user_logger = config['configurable'].get('logger')

            prompt = PromptTemplate(input_variables=['chat_history','user_input','ai_response'],template=message)
            class conversation(BaseModel):
                end_conversation : str = Field(default='no',description="Return yes if the flow ends otherwise keep it as no")
            llm_strcd = self.llm.with_structured_output(conversation)
            chain = prompt | llm_strcd
            user_logger.info(f"Getting response from conversation_end_llm")
            # response = chain.invoke({'chat_history':chat_history,'user_input':user_input,'ai_response':ai_response})
            response = await retry_with_backoff(user_logger,chain.invoke,{'chat_history':chat_history,'user_input':user_input,'ai_response':ai_response})
            return {"conversation_end":response.end_conversation}
        except Exception as e:
            user_logger.exception("Error occured in - conversation_end_llm generating response",error = str(e))
            raise        
                
    ## Routing functions
    @staticmethod
    async def invalid_router(state:MessagesState,config:RunnableConfig):
        user_logger = config['configurable'].get('logger')
        try:    
            if state['valid'] =='yes':
                return 'yes'
            else: 
                return 'no'    
        except Exception as e:
            user_logger.exception("Error occured in - Invalid router",error = str(e))
            raise

    @staticmethod
    async def flow_router(state:MessagesState,config:RunnableConfig):
        flow = state.get('flow_type','offtable')
        if flow =='ontable':
            return 'ontable'
        else:
            return 'offtable'


class data_update_flow:
    def __init__(self,config):
        self.llm = CreateLLM.openai_llm()
        # self.llm = CreateLLM.gemini_llm()
        self.conninfo = db_conninfo()
        self.prompts = load_yaml().get('data_update','')
        self.config = config

    async def user_profile(self,state:DataUpdate,config:RunnableConfig):
        old_user_profile = state.get('old_user_profile',"")
        chat_history = state.get('chat_history',[])
        message = self.prompts.get('profile_update')
        prompt = PromptTemplate(input_variables=['chat_history','old_profile'],template=message)
        structured_llm = self.llm.with_structured_output(UserProfile)
        chain = prompt | structured_llm
        user_logger=config['configurable'].get('logger')
        try:
            # Trying to invoke the chain
            user_logger.info(f"Updating user profile")
            response = await retry_with_backoff(user_logger,chain.invoke,input = {'chat_history': chat_history, 'old_profile': old_user_profile})
            chat_summary = await retry_with_backoff(user_logger,summarize_memory2,chat_history) 
            return {'new_user_profile' : response.__dict__, 'chat_summary': chat_summary['chat_summary']}
            # response = chain.invoke({'chat_history': chat_history, 'old_profile': old_user_profile})
        except Exception as e:
            user_logger.exception(f"Failed to get a valid response in user_profile",error=str(e))
            # Catch other exceptions and retry
        
    @staticmethod
    async def data_uploader(state:DataUpdate,config : RunnableConfig):
        try:
            user_data = state.get('new_user_profile')
            chat_history = state.get('chat_history')
            chat_summary = state.get('chat_summary','')
            client_id = config['metadata']['client_id']
            user_id = config['metadata']['user_id']
            session_id = config['configurable']['thread_id']
            type = config['metadata'].get('use_case','')
            user_logger = config['configurable'].get('logger')
            async def _data_uploader():
                conn = await asyncpg.connect(user=os.getenv('PSQL_USERNAME'),password=os.getenv('PSQL_PASSWORD'), 
                    database=os.getenv('PSQL_DATABASE'),host=os.getenv('PSQL_HOST'))

                insert_userdetial_query = """
                INSERT INTO general_information.user_profile ( user_id, client_id, name, age, address, preferences, gender) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, client_id) DO UPDATE SET name = EXCLUDED.name, age = EXCLUDED.age,
                address = EXCLUDED.address, preferences = EXCLUDED.preferences, gender = EXCLUDED.gender;
                """
                await conn.execute(
                    insert_userdetial_query,
                    user_id,client_id,user_data['name'],user_data['age'],user_data['address'], user_data['preferences'], user_data['gender']
                )

                insert_chat_query = """INSERT INTO chats.user_chat_history (user_id, session_id, type, client_id, chat_summary, chat_history)
                VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id, session_id, client_id)
                DO UPDATE SET
                    type = EXCLUDED.type,
                    chat_summary = EXCLUDED.chat_summary,
                    chat_history = EXCLUDED.chat_history,
                    date_time = now()
                """ 
                await conn.execute(insert_chat_query,user_id,session_id,type,client_id,chat_summary,json.dumps(chat_history))
                await conn.close()
            user_logger.info('Uploading data')    
            await retry_with_backoff(user_logger,_data_uploader)
            user_logger.info('Data upload complete')  

        except Exception as e:
            user_logger.exception("Failed to upload data",error=str(e))
            raise

    def analysis(self):
        type = self.config['metadata']['use_case'].split('_')[0].lower()
        analyze_fn = AnalyzerRegistry.get_analyzer(type)
        async def analyzer_node(state:DataUpdate, config:RunnableConfig):
            return await analyze_fn(self.llm,self.prompts, state, config)  # ✅ Accepts state, config
        return analyzer_node
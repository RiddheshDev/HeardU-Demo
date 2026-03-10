from pydantic import BaseModel , Field
from src.langgraph.states import *
from src.langgraph.func import *
from src.langgraph.utilits import retry_with_backoff
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableConfig
from textwrap import dedent
from langchain_core.prompts import PromptTemplate
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from src.langgraph.LLMs import *
import asyncio
import psycopg2
from psycopg2.extras import execute_values

class AnalyzerRegistry:
    def __init__(self):
        # self.llm = CreateLLM.gemini_llm()
        pass
    
    @staticmethod
    async def restaurant_feedback(llm,prompts, state:DataUpdate, config: RunnableConfig):
        flow_type = state.get('flow_type','offtable')
        async def _restaurant_feedback_offtable():
            try :
                user_logger = config['configurable'].get('logger')
                user_logger.info(f"Analysis flow started - {config['metadata']['use_case']}")
                chat_history = state.get('chat_history','')
                message = prompts['restaurant_analysis']
                prompt = PromptTemplate(input_variables=['chat_history'],template=message)
                llm_with_structured_opt = llm.with_structured_output(restaurant_output,method="function_calling")
                chain = prompt | llm_with_structured_opt
                # response = await chain.ainvoke({'chat_history':chat_history})
                response = await retry_with_backoff(user_logger,chain.ainvoke,input={'chat_history':chat_history})
                response = response.__dict__  
                async def _upsert_data():
                    user_logger.info('Uploading data')
                    # print("???????????????????????????????????????????????????")
                    # print('response',response,flush=True)
                    # conn = await db_conn()
                    async with db_conn() as conn:
                        insert_query = """insert into analysis.restaurant (user_id, session_id, type, client_id, chat_history, chat_summary, emotions,
                        review_rating, food, food_rating, service, service_rating, menu, menu_rating, staff, staff_rating, ambiance, ambiance_rating, pricing, 
                        pricing_rating, wait_time, wait_time_rating, hygiene, hygiene_rating, others, others_rating, nps) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                        $10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)"""
                        
                        await conn.execute(insert_query,config['metadata']['user_id'],config['configurable']['thread_id'],config['metadata']['use_case'],
                                config['metadata']['client_id'],json.dumps(state['chat_history']),response['summary'],response['emotions'],response['review_rating'],
                                response['food'],response['food_rating'],response['service'],response['service_rating'],response['menu'],response['menu_rating'],
                                response['staff'],response['staff_rating'],response['ambiance'],response['ambiance_rating'],response['pricing'],response['pricing_rating'],
                                response['wait_time'],response['wait_time_rating'],response['hygiene'],response['hygiene_rating'],response['others'],response['others_rating'],response['nps'])
                        user_logger.info('Data upload complete')  
                    user_logger.info(f"Analysis flow complete - {config['metadata']['use_case']}")
                await retry_with_backoff(user_logger,_upsert_data)
            
            except Exception as e:
                user_logger.exception("Failed to upload data",error=str(e))
                raise

        async def _restaurant_feedback_ontable():
            try:    
                chat_history = state.get('chat_history','None')
                metadata       = config.get('metadata', {})
                configurable   = config.get('configurable', {})
                client_id      = metadata.get('client_id')
                user_id        = metadata.get('user_id')
                thread_id      = configurable.get('thread_id')
                user_logger    = configurable.get('logger')
                message = prompts.get('restaurant_analysis_ontable')
                prompt  = PromptTemplate(input_variables=['chat_history'], template=message)
                
                chain = prompt | llm | JsonOutputParser()
                # response = chain.invoke({'chat_history':chat_history})
                response = await retry_with_backoff(user_logger,func=chain.invoke,input={'chat_history':chat_history})
                
                # print(response)
                async with db_conn() as conn:
                    insert_query = """insert into analysis.suggestions (client_id, user_id, thread_id, comment,
                    type, aspect, flow)
                    values ($1,$2,$3,$4,$5,$6,$7) """
                    await conn.execute(insert_query,client_id,user_id,thread_id,response.get('comment'),'complaint',response.get('aspect'),'ontable')
            except Exception as e:
                user_logger.exception('Failed analyzing and uploading data',error = str(e))
                raise 

        async def upload_data():
            try:        
                # Extract metadata once
                metadata       = config.get('metadata', {})
                configurable   = config.get('configurable', {})
                client_id      = metadata.get('client_id')
                user_id        = metadata.get('user_id')
                thread_id      = configurable.get('thread_id')
                use_case       = metadata.get('use_case')
                chat_history   = state.get('chat_history')
                data           = []
                message        = prompts['recommendation']
                user_logger    = config['configurable'].get('logger')

                # Prepare prompt and llm pipeline (assuming these are helper objects)
                prompt  = PromptTemplate(input_variables=['chat_history'], template=message)
                chain = prompt | llm | JsonOutputParser()
                
                # Get response from chain
                # response = chain.invoke({'chat_history': chat_history})
                response = await retry_with_backoff(user_logger,chain.invoke,input={'chat_history': chat_history})
                # print('\n\nresponse\n',response)
                # Process suggestions with type 'suggestion'
                suggestions = response.get('suggestions') or []
                if isinstance(suggestions,list):
                    data.extend({'client_id': client_id,'user_id': user_id,
                        'thread_id': thread_id,'use_case': use_case,
                        'comment': s.get('comment'),'type': 'suggestion',
                        'aspect': s.get('aspect')} for s in suggestions if isinstance(s,dict))

                # Process complaints with type 'complaint'
                complaints = response.get('complaints') or []
                if isinstance(complaints,list):
                    data.extend({
                        'client_id': client_id,'user_id': user_id,'thread_id': thread_id,
                        'use_case': use_case,'comment': c.get('comment'),'type': 'complaint',
                        'aspect': c.get('aspect'),'priority': c.get('priority')} for c in complaints if isinstance(c,dict))

                if not data:
                    print("No feedback data to insert.")
                    return

                columns = ['client_id', 'user_id', 'thread_id', 'use_case', 'comment', 'type', 'aspect', 'priority']
                values = [tuple(d.get(col) for col in columns) for d in data]

                try:
                    def _upsert_data():
                        with psycopg2.connect(db_uri2()) as conn:
                            with conn.cursor() as cursor:
                                insert_query = f"""
                                    INSERT INTO analysis.suggestions ({', '.join(columns)})
                                    VALUES %s
                                """
                                execute_values(cursor, insert_query, values)
                                conn.commit()    
                    await retry_with_backoff(user_logger,_upsert_data)
                except Exception as e:
                    # Log the error
                    print(f"Error while inserting data: {e}")
                    raise
            except Exception as e:
                user_logger.exception(f"Failed to get suggestions and complaints.",error=str(e))
                raise

        if flow_type =='ontable':
            await asyncio.gather(_restaurant_feedback_ontable())   
        else:         
            await asyncio.gather(_restaurant_feedback_offtable(),upload_data())

    @staticmethod
    def get_analyzer(use_case: str):  
        mapping = {
            "restaurant": AnalyzerRegistry.restaurant_feedback,
            "housing": AnalyzerRegistry.housing_feedback,
            "b2c": AnalyzerRegistry.b2c_feedback,
        }
        return mapping.get(use_case)
    

class ToolOutputValidator:
    def __init__(self):
        # self.llm = CreateLLM.gemini_llm()
        pass
    
    @staticmethod
    async def b2c_output_validator(llm,state:ToolState,config:RunnableConfig):
        try:
            user_logger = config['configurable'].get('logger')
            user_logger.info("Output Validating - b2c")
            sql_output = state.get('sql_output','')
            semantic_output = state.get('semantic_output','')
            print('sql_output',sql_output,flush=True)
            
            unique_products = {}
            # Ensure both are lists
            if not isinstance(sql_output, list):
                sql_output = []
            if not isinstance(semantic_output, list):
                semantic_output = []

            for product in sql_output:
                unique_products[product['product_id'] ] = product

            for product in semantic_output:
                if product['product_id'] not in unique_products:
                    unique_products[product['product_id']] =  product
            # print('Unique products',unique_products,flush=True)
            if not unique_products:
                return {'products': 'none'}
            message = dedent(""" You are a smart verification agent. You need to check the list of products to get the products that matches the users query.
                            and get the product_id for those product_ids
                            <product_list> {products} </product_lists>

                            user_query : {user_query} 
                            """)
            prompt = PromptTemplate(input_variables=['products','user_query'],template=message)
            class Output(BaseModel):
                product_id : Optional[List[str]] = Field(description=" Get the list of product_id that matches user's query")
            llm_strct = llm.with_structured_output(Output,method="function_calling")
            chain = prompt| llm_strct
            response = await retry_with_backoff(user_logger,chain.invoke,input={'products': unique_products,'user_query':state.get('user_input','')})
            # response = chain.invoke({'products': unique_products,'user_query':state.get('user_input','') })
            # print("Raw LLM response:", response,flush=True)
            product_list = [
            {k: v for k, v in unique_products[pid].items() if k not in ('product_id', 'client_id')}
            for pid in response.product_id if pid in unique_products]
            return {'products':product_list}
        except Exception as e:
            user_logger.exception("Failed Output Validating - b2c",error=type(e))
            raise

    @staticmethod
    async def housing_output_validator(llm,state:ToolState,config:RunnableConfig):
        try:
            user_logger=config['configurable'].get('logger')
            user_logger.info("Output Validating - housing")
            sql_output = state.get('sql_output','')
            semantic_output = state.get('semantic_output','')

            unique_events = {}
            # Ensure both are lists
            if not isinstance(sql_output, list):
                sql_output = []
            if not isinstance(semantic_output, list):
                semantic_output = []

            for event in sql_output:
                unique_events[event['event_id'] ] = event

            for event in semantic_output:
                if event['event_id'] not in unique_events:
                    unique_events[event['event_id']] =  event

            if not unique_events:
                return {'events': 'none'}
            message = dedent(""" You are a smart verification agent. You need to check the list of events/meetings to get the events/meetings that matches the users query
                            and get the event_id of those related events.
                            <event_list> {events} </event_list>

                            user_query : {user_query} 
                            """)
            prompt = PromptTemplate(input_variables=['events','user_query'],template=message)
            class Output(BaseModel):
                event_id : Optional[List[str]] = Field(description=" Get the list of event_id that matches user's query")
            llm_strct = llm.with_structured_output(Output,method="function_calling")
            chain = prompt| llm_strct
            response = await retry_with_backoff(user_logger,chain.invoke,input = {'events': unique_events, 'user_query': state.get('user_input','')})
            # response = chain.invoke({'events': unique_events, 'user_query': state.get('user_input','') })
            # print("Raw LLM response:", response)
            event_list = [
            {k: v for k, v in unique_events[cid].items() if k not in ('event_id', 'client_id')}
            for cid in response.event_id if cid in unique_events]
            return {'events': event_list}
        
        except Exception as e:
            user_logger.exception("Failed Output Validating - housing",error=type(e))
            raise

    @staticmethod
    def get_analyzer(use_case: str):
        mapping = {
            "b2c": ToolOutputValidator.b2c_output_validator,
            "housing": ToolOutputValidator.housing_output_validator
        }
        return mapping.get(use_case)
    
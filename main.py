from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import os
import asyncio
import urllib.parse
import uuid
import sys
import nest_asyncio
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.langgraph.graphs import GraphBuilder , DataUpdateGraph
from src.langgraph.nodes import get_inactive_thread_ids
from contextlib import asynccontextmanager
import asyncpg
import json
nest_asyncio.apply()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()


templates = Jinja2Templates(directory="templates")

# DB and Graph Setup
password_encoded = urllib.parse.quote(os.getenv("PSQL_PASSWORD"))
conninfo = (
    f"postgres://{os.getenv('PSQL_USERNAME')}:{password_encoded}"
    f"@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"
    f"?sslmode={os.getenv('PSQL_SSLMODE')}"
)

compiled_graphs = {}
pg_pool = None
session_id = {}
restaurant = 'chinese wok'
location = 'goregaon'

async def get_pg_pool():
    global pg_pool
    if pg_pool is None or pg_pool._closed:
        pg_pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=20,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            }
        )
        await pg_pool.open()
    return pg_pool

async def process_message(user_input,metadata):
    user_id, agent_type, location, client = metadata['user_id'], metadata['use_case'], metadata['location'], metadata['client'] ##can be updated later
    config = {
        "recursion_limit": 10,"configurable" : {},
        'metadata':{'user_id':user_id,'use_case':agent_type,
                    'client':client,'location':location}}
    if f'{user_id}_{agent_type}_{client}' not in session_id:
        session_id[f'{user_id}_{agent_type}_{client}'] = str(uuid.uuid4())
    config['configurable']['thread_id'] = session_id[f'{user_id}_{agent_type}_{client}']    
    
    pool = await get_pg_pool()
    checkpointer = AsyncPostgresSaver(pool)
    # await checkpointer.setup()
    if config['metadata']["use_case"] not in compiled_graphs:
        graph_builder = GraphBuilder(config=config)
        compiled_graphs[config['metadata']["use_case"]] = graph_builder.compile_graph(memory=checkpointer)
        print("*" * (20), 'Compiling Done',compiled_graphs, "*" * (20))
    graph = compiled_graphs[config['metadata']["use_case"]]
    await graph.ainvoke({"user_input": user_input}, config)
    memory = await checkpointer.aget(config)
    end_convo = memory['channel_values']['conversation_end']
    if end_convo == 'yes':
        update_graph_builder = DataUpdateGraph(config=config)
        update_graph = update_graph_builder.compile_graph(memory=checkpointer)
        await update_graph.ainvoke({'old_user_profile':memory['channel_values']['user_profile'],
                                    "chat_history":memory['channel_values']['chat_history'],
                                    'chat_summary':memory['channel_values']['chat_summary']}
                                    ,config)
        session_id.pop(f'{user_id}_{agent_type}_{client}', None)
        return memory['channel_values'].get('ai_response', "No response.")
    return memory['channel_values'].get('ai_response', "No response.")

async def end_conversation(target_thread_id,metadata):
    try:
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        config = {'configurable':{'thread_id':target_thread_id},'metadata':metadata}
        pool = await get_pg_pool()
        checkpointer = AsyncPostgresSaver(pool)
        memory = await checkpointer.aget(config)
        update_graph_builder = DataUpdateGraph(config=config)
        update_graph = update_graph_builder.compile_graph(memory=checkpointer)
        await update_graph.ainvoke({'old_user_profile':memory['channel_values']['user_profile'],
                                    "chat_history":memory['channel_values']['chat_history'],
                                    'chat_summary':memory['channel_values']['chat_summary']}
                                    ,config)
        await delete_inactive_threads_from_db(inactive_thread_ids=target_thread_id)
        print(f'Deleted sessions for user {metadata['user_id']}')
        try:
            session_id.pop(f'{metadata['user_id']}_{metadata['use_case']}_{metadata['client']}', None)
        except:
            print("Session doesn't exist")
    except Exception as e:
        # print("Session doesn't exist")
        print(f'Failed to delete sessions : {e}')
        pass

async def delete_inactive_threads_from_db(inactive_thread_ids):
    conn = await asyncpg.connect(
        user=os.getenv('PSQL_USERNAME_AWS'),
        password=os.getenv('PSQL_PASSWORD_AWS'),
        database=os.getenv('PSQL_DATABASE_AWS'),
        host=os.getenv('PSQL_HOST_AWS')
    )
    
    # Create a query to delete multiple threads at once (using `IN` SQL)
    query = """
    delete from sessions.checkpoints where thread_id = $1
    """
    
    try:
        # Execute the delete query, passing the inactive thread_ids
        await conn.execute(query, inactive_thread_ids)
        print(f"Deleted {inactive_thread_ids} inactive threads from DB.")
    except Exception as e:
        print(f"Error deleting inactive threads from DB: {e}")
    finally:
        await conn.close()


async def handle_inactive_sessions():
    try:
        thread_metadata_dict = await get_inactive_thread_ids()

        if not thread_metadata_dict:
            print("No inactive sessions found.")
            return
        
        tasks = []
        for thread_id, metadata in thread_metadata_dict.items():
            tasks.append(end_conversation(thread_id, metadata))

        # Now gather all tasks concurrently
        await asyncio.gather(*tasks)
        print(f"Processed {len(tasks)} inactive sessions.")

    except Exception as e:
        print(f"Error handling inactive sessions: {str(e)}")

async def schedule_inactive_cleanup(interval_seconds=40):
    while True:
        print("*"*(20),"Cleaning sessions","*"*(20))
        await handle_inactive_sessions()
        await asyncio.sleep(interval_seconds)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start your background task
    asyncio.create_task(schedule_inactive_cleanup())
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# Routes
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/", response_class=HTMLResponse)
async def post_index(request: Request, user_id: str = Form(...), use_case: str = Form(...),client:str=Form(...),location:str=Form(...)):
    request.session['user_id'] = user_id
    request.session['use_case'] = use_case
    request.session['client'] = client
    request.session['location'] = location
    return RedirectResponse(url="/chat", status_code=303)

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request):
    if "user_id" not in request.session or "use_case" not in request.session:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("chat.html", {"request": request, "response": None})

@app.post("/chat", response_class=HTMLResponse)
async def post_chat(request: Request, user_input: str = Form(...)):
    if "user_id" not in request.session or "use_case" not in request.session:
        return RedirectResponse("/", status_code=303)
    user_id    = request.session["user_id"]
    use_case = request.session["use_case"]
    client = request.session['client']
    location   = request.session['location']
    metadata = {'user_id':user_id,'use_case':use_case,'client':client,'location':location}
    try:
        response = await process_message(user_input, metadata)
    except Exception as e:
        response = f"Error: {str(e)}"

    return templates.TemplateResponse("chat.html", {"request": request, "response": response})

# Optional: Close pool on shutdown
# @app.on_event("shutdown")
# async def shutdown():
#     if pg_pool and not pg_pool._closed:
#         await pg_pool.close()

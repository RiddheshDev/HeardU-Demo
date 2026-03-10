from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI ,OpenAIEmbeddings
import os
import openai
from typing import Optional
import yaml
load_dotenv()

class CreateLLM:
    def __init__(self,config :Optional[dict] = None):
        os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY')
        openai.api_key = os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY") 
        self.config : dict = config if config is not None else {}
    @staticmethod  
    def groq_llm(model):
        # model = self.config.get(model, 'qwen-2.5-32b')
        # os.environ['GROQ_API_KEY'] = os.getenv("GROQ_API_KEY")
        # print("="*(30)+'Api Key : '+os.environ['GROQ_API_KEY']+"="*(30))  # Default to 'qwen-2.5-32b' if model key is missing
        return ChatGroq(model=model, temperature=0.5)
    
    # def evaluation_llm(self):
    #     model = self.config.get('model','qwen-2.5-32b')
    #     return ChatGroq(model = model , temperature= 0.5)
    @staticmethod
    def gemini_llm():
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash")  
     
    @staticmethod
    def openai_llm(model = None,embeddings = False):
        if model and embeddings:
            return OpenAIEmbeddings(model=model)

        if model :
            return ChatOpenAI(model=model)    
        
        return ChatOpenAI(model='gpt-4.1-2025-04-14')

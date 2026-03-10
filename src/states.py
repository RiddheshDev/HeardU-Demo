from typing import Annotated, List ,Literal ,TypedDict ,Optional 
from langgraph.graph.message import MessagesState ,add_messages # type: ignore
from langchain_core.messages import AnyMessage, HumanMessage ,AIMessage , ToolMessage
from pydantic import BaseModel, Field

##Used in Agent
class MessagesState(TypedDict):
    user_input : str
    ai_response : str   
    messages:  Annotated[list[AnyMessage],add_messages]
    chat_history : list[dict]
    chat_history_w_tool : list[dict] 
    chat_summary : str
    tool_output : Annotated[list[AnyMessage],add_messages]
    tool_output_filtered : list
    tool_name : str     
    tool_called : bool  #Use like a tool on of swtich
    user_profile_loaded : str
    user_profile : dict
    client : dict
    first_time_user : bool
    conversation_end : str
    valid : str
    old_chat_summary : str
    products : Optional[dict]  
    coupon : Optional[dict]  
    flow_type : str

##Used in SQL_graph
class ToolState(TypedDict):
    messages: list[any]
    client_id : Optional[int]
    sql_output : Optional[dict]
    semantic_output : Optional[dict]   
    products : Optional[dict]
    user_input : str
    events : Optional[dict]

##Used to fetch user profile from chat
class UserProfile(BaseModel):
    name: Optional[str] = Field(default=None, description="Name of the user")
    age: Optional[int] = Field(default=None, description="Age of the user")
    gender: Optional[str] = Field(default=None, description="Gender of the user")
    preferences: Optional[str] = Field(default=None, description="Preferences of the user; can add more to existing or can update.")
    address: Optional[str] = Field(default=None, description="Address of the user; can add more to existing or can update.")

##Used to create new user_profile from user chats
class DataUpdate(TypedDict):
    old_user_profile : dict
    new_user_profile : dict
    chat_history : list
    chat_summary : str
    flow_type : str

##Ingate function
class InGate(BaseModel):
    valid : Optional[str] = Field(description="if valid return yes or else return no")
    ai_response : Optional[str] = Field(description="AI's formal response declining request")

##Memory
class Memory(BaseModel):
    chat_summary : Optional[str] = Field(description="Return chat_summary")

## Analyzing Data option.
class restaurant_output(BaseModel):
    emotions         : Optional[str] = Field(default=None, description="Emotion behind users feedback: happy, satisfied, neutral, angry, frustrated, disgusted")
    nps              : Optional[int] = Field(default=None, description="Implicit NPS score estimated from feedback, scale of 0–10")

    summary          : Optional[str] = Field(default=None, description="Summarize the whole feedback in detail.")
    review_rating    : Optional[int] = Field(default=None, description="Rate the overall feedback from 1-5")

    food             : Optional[str] = Field(default='NA', description="Summarize food feedback else NA")
    food_rating      : Optional[int] = Field(default=None, description="Rate the food feedback from 1-5")

    service          : Optional[str] = Field(default='NA', description="Summarize service feedback else NA")
    service_rating   : Optional[int] = Field(default=None, description="Rate the service feedback from 1-5")

    menu             : Optional[str] = Field(default='NA', description="Summarize menu feedback else NA")
    menu_rating      : Optional[int] = Field(default=None, description="Rate the menu feedback from 1-5")

    staff            : Optional[str] = Field(default='NA', description="Summarize staff feedback else NA")
    staff_rating     : Optional[int] = Field(default=None, description="Rate the staff feedback from 1-5")

    ambiance         : Optional[str] = Field(default='NA', description="Summarize ambiance feedback else NA")
    ambiance_rating  : Optional[int] = Field(default=None, description="Rate the ambiance feedback from 1-5")

    pricing          : Optional[str] = Field(default='NA', description="Summarize pricing feedback else NA")
    pricing_rating   : Optional[int] = Field(default=None, description="Rate the pricing feedback from 1-5")

    wait_time        : Optional[str] = Field(default='NA', description="Summarize wait times feedback else NA")
    wait_time_rating : Optional[int] = Field(default=None, description="Rate the wait times feedback from 1-5")

    hygiene          : Optional[str] = Field(default='NA', description="Summarize hygiene feedback else NA")
    hygiene_rating   : Optional[int] = Field(default=None, description="Rate the hygiene feedback from 1-5")

    others           : Optional[str] = Field(default='NA', description="Additional comments, if any else NA")
    others_rating    : Optional[int] = Field(default=None, description="Rate the additional comments from 1-5")


class b2c_output(BaseModel):
    emotions      : Optional[str] = Field(default=None, description="Emotion behind users feedback: happy, satisfied, neutral, angry, frustrated, disgusted")
    nps           : Optional[int] = Field(default=None, description="Implicit NPS score estimated from feedback, scale of 0–10")

    summary       : Optional[str] = Field(default=None, description="Summarize the whole feedback in detail.")
    review_rating : Optional[int] = Field(default=None, description="Rate the overall feedback from 1-5")
    

class housing_output(BaseModel):
    location_detail : Optional[str] = Field(default='NA',description="Location of the complain if provided.")
    feedback_type   : Optional[str] = Field(default='NA',description="Return type as 'enquiry' , 'complaint', 'praise'.")
    feedback_title  : Optional[str] = Field(default='NA',description="An explanatory title for the provided feedback.")
    description     : Optional[str] = Field(default='NA',description="Description based on the feedback")
    ai_solution     : Optional[str] = Field(default='NA',description="AI based solution about the complaint else none")
    severity        : Optional[str] = Field(default='NA', description= "Severity of the complaint as 'low','medium', 'low'. " )
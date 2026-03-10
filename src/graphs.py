from langgraph.prebuilt import ToolNode, tools_condition  # type: ignore
from langgraph.graph import  StateGraph, START, END # type: ignore
from src.langgraph.states import *
from langgraph.checkpoint.memory import MemorySaver # type: ignore
from src.langgraph import nodes 

class GraphBuilder:
    def __init__(self,config):
        self.config = config
        # self.memory = MemorySaver()
        # Get the logger from config that's being passed through process_message 
        self.logger = self.config['configurable'].get('logger')
        if not self.logger:
            # Fallback logger if not provided
            from src.langgraph.logger_config import logger
            self.logger = logger
        self.logger.info(f"GraphBuilder initialized For use case -{self.config['metadata'].get('use_case')} ", 
                         use_case=self.config['metadata'].get('use_case'))
        
    def restaurant_feedback_graph(self):
        """Build the restaurant feedback workflow graph"""
        self.logger.info("Starting restaurant feedback graph construction")
        try:
            ## Initialize agent nodes
            self.logger.info("Initializing agent nodes")
            agent_nodes = nodes.restaurant_feedback(config=self.config)

            ## Create state graph
            self.logger.info("Creating StateGraph with MessagesState")
            self.graph_builder =StateGraph(MessagesState)
            ##Add nodes to graph
            self.logger.info("Adding nodes to graph")
            # self.graph_builder.add_node('ingate',agent_nodes.ingate)
            self.graph_builder.add_node('ingate',agent_nodes.ingate_node())
            self.graph_builder.add_node('flow_agent',agent_nodes.flow_agent)   
            self.graph_builder.add_node('agent',agent_nodes.agent)
            self.graph_builder.add_node('agent2',agent_nodes.agent2)         
            tools_node = ToolNode(agent_nodes.tools,messages_key ='tool_output')
            self.graph_builder.add_node('tools_node',tools_node)
            self.graph_builder.add_node('tool_data_updated',agent_nodes.tool_data_updated)
            self.graph_builder.add_node('conversation',agent_nodes.conversation_end)
            self.logger.info("All nodes added successfully")
            ## Adding edges to graphs
            self.logger.info("Adding edges to graph")
            self.graph_builder.add_edge(START,'ingate')
            self.graph_builder.add_conditional_edges('ingate',agent_nodes.invalid_router,{'no':END,'yes':'flow_agent'}) 
            # self.graph_builder.add_conditional_edges('ingate',agent_nodes.invalid_router,{'no':END,'yes':'agent'})
            self.graph_builder.add_conditional_edges('flow_agent',agent_nodes.flow_router,{"offtable":"agent",'ontable':'agent2'})  
            self.graph_builder.add_conditional_edges('agent',tools_condition,{'tools': 'tools_node',END:'conversation'})
            self.graph_builder.add_edge('agent2','conversation')   
            self.graph_builder.add_edge('tools_node','tool_data_updated')
            self.graph_builder.add_edge('tool_data_updated','agent')
            # graph_builder.add_edge('agent','conversation')
            self.graph_builder.add_edge('conversation',END)
            self.logger.info("All edges added successfully")
            self.logger.info("Restaurant feedback graph construction completed")
            # print(graph.get_graph().draw_mermaid(),flush=True)
        except Exception as e:
            self.logger.error("Error constructing restaurant_feedback_graph", 
                            error=str(e), 
                            error_type=type(e).__name__, 
                            exc_info=True)
            raise


    def compile_graph(self,memory):
        """Compile the graph based on use case with memory/checkpointer"""
        try:
            usecase = self.config['metadata'].get('use_case')
            self.logger.info("Starting graph compilation", use_case=usecase)
            print('Usecase' ,usecase,flush=True)

            ## Build the approriate graph based on the use case.
            if usecase == "housing":
                self.logger.info("Building housing_wo_rag_graph")
                self.housing_feedback_graph()

            elif usecase == "housing_agent_w_rag":
                self.logger.info("Building housing_w_rag_graph")
                self.housing_w_rag_graph()

            elif usecase == 'restaurant':
                self.logger.info("Building restaurant_feedback_graph")
                self.restaurant_feedback_graph()

            elif usecase == 'b2c':
                self.logger.info("Building b2c_feedback_graph")
                self.b2c_feedback_graph()

            else:
                self.logger.warning(f"Unknown use case detected - {usecase}", 
                                  use_case=usecase)
                # You might want to raise an exception here or have a default graph
                raise ValueError(f"Unknown use case: {usecase}")
            
            # Compile the graph with memory
            self.logger.info("Compiling graph with checkpointer")
            compiled_graph = self.graph_builder.compile(checkpointer=memory)
            
            self.logger.info("Graph compilation successful", use_case=usecase)
            return compiled_graph

        except Exception as e:
            self.logger.error("Error during graph compilation", 
                        error=str(e), 
                        error_type=type(e).__name__, 
                        usecase=usecase,
                        exc_info=True)
            raise

class DataUpdateGraph:
    def __init__(self,config):
        # self.graph_builder = StateGraph(MessagesState)
        self.config = config
        self.logger = self.config['configurable'].get('logger')
        if not self.logger:
            # Fallback logger if not provided
            from src.langgraph.logger_config import logger
            self.logger = logger
        # self.memory = MemorySaver()

    def data_update_flow_graph(self):
        """Build the data update flow graph"""
        self.logger.info("Starting data_update_flow_graph construction")
        try:
            # Initialize agent nodes
            self.logger.info("Initializing agent nodes")
            agent_nodes = nodes.data_update_flow(self.config)
            # Create state graph
            self.logger.info("Creating StateGraph with DataUpdate state")
            self.graph_builder = StateGraph(DataUpdate)
            # Add nodes with logging
            self.logger.info("Adding nodes to graph")
            self.graph_builder.add_node('profile_update', agent_nodes.user_profile)
            self.graph_builder.add_node('data_upload',agent_nodes.data_uploader)
            self.graph_builder.add_node('analysis',agent_nodes.analysis())
            self.logger.info("All nodes added successfully")

            # Add edges with logging
            self.logger.info("Adding edges to graph")
            self.graph_builder.add_edge(START,'profile_update')
            self.graph_builder.add_edge('profile_update','data_upload')
            self.graph_builder.add_edge('data_upload','analysis')
            self.graph_builder.add_edge('analysis',END)
            self.logger.info("All edges added successfully")
            self.logger.info("Data update flow graph construction completed")
        except Exception as e:
                self.logger.error("Error constructing data_update_flow_graph", 
                                error=str(e), 
                                error_type=type(e).__name__, 
                                exc_info=True)
                raise
        
    def compile_graph(self,memory = None):
        """Compiling the Data Update flow graph"""
        try:
            ## Compiling the graph of data update.
            self.logger.info("Building Data update flow graph.")
            self.data_update_flow_graph()
            self.logger.info("Graph compiling done for graph - data update")
            compiled_graph = self.graph_builder.compile(checkpointer=memory)
            return compiled_graph
        
        except Exception as e:
            self.logger.error("Error during Dataupdate graph compilation ",
                              error = str(e),
                              error_type=type(e).__name__,
                              exc_info = True
                              )
            raise
    
            
    




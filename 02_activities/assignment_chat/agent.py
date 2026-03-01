print(" -------------------- COMMENCE THE ASSIGNMENT --------------------------")
print(" --- Imports start...")
from langchain.tools import tool
from langchain.chat_models import init_chat_model
import os
import io
print(" --- 30%...")
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timedelta, date
import requests
import duckdb
from pandas import DataFrame
print(" --- 60%...")
from langchain_core.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
from langchain_core.messages import SystemMessage
print(" --- 90%...")
import operator
from pydantic import BaseModel, Field
import re
import http.client, urllib.parse
import news_api_caller
import sys
import traceback
from langchain_tavily import TavilySearch

print(" --- 100% - Imports are done...")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "assignment_chat\\.secrets")
openai_key = os.getenv('API_GATEWAY_KEY')
mediastack_key = os.getenv('API_MEDIASTACK_KEY')
tavily_key = os.getenv('API_TAVILY_KEY')

model = init_chat_model(
    "openai:gpt-4o-mini",
    temperature=0.7,
    base_url='https://k7uffyg03f.execute-api.us-east-1.amazonaws.com/prod/openai/v1', 
    api_key='any value',
    default_headers={"x-api-key": openai_key}
)

tavily_search = TavilySearch(tavily_api_key=tavily_key, max_results=10)

print(" --- Model ready! - Loading data...")


print("Connecting to Mediastack...")
mediastack = http.client.HTTPConnection('api.mediastack.com')
print("MediaStack connected!")


day = datetime.now().date()
success = False
for i in range(5):
    if success:
        break
    date_str = day.strftime("%Y%m%d")
    print(date_str)
    source_url = f"https://data.opensanctions.org/datasets/{date_str}/sanctions/targets.simple.csv"
    try:
        response = requests.get(source_url)
        success = True
    except requests.exceptions.RequestException as e:
        print("Error occured, trying previous day")
        i += 1
        day = day - timedelta(days=1)

if not success:
    print("Could not get the data; Exit")
    exit(1)

content = response.content
file_object = io.BytesIO(content)

data_file_name = "data.csv"
with open(data_file_name, "wb") as f:
    f.write(content)

db = duckdb.connect()

print(" --- Data loaded!")

### FUNCS TO GET THINGS FROM CSV TABLE VIA SQL QUERRIES ###

import country_converter
def approx_tokens(text: str) -> int:
    return len(text) // 4

def resolve_db_result(df: DataFrame):
    token_count = approx_tokens(df.to_string())
    within_limit = token_count < 228000
    if(token_count >= 228000):
        print("TOO MUCH ------------------------")
        return (df, within_limit)
    else:
        return (df.to_string(), within_limit)


class UserRequestInfo(BaseModel):
    names_to_search_for: list[str]=Field(description="All possible names user might be interested in combined with possible misspellings, including if present: Last Name, Organization name, etc. DO NOT INCLUDE FIRST NAMES OF HUMANS. You should try to resolve the misspellings, give all logical possibilities into this array.")
    user_wants_human: bool=Field(description="Whether user wants to find Human Being's data specifically")
    user_wants_organization: bool=Field(description="Whether user wants to find Organization specifically")
    user_wants_specific_country: bool=Field(description="Whether user wants to limit the resuls by a set of countries.")
    countries: list[str]=Field(description="A list of countries that user mentioned. Empty if none.")
    user_wants_news: bool=Field(description="Whether user wanted to look for recent news")
    first_names: list[str]=Field(description="A list of all first names that got accidentally added to names_to_search_for")

class LastNamesOrOrganizationsOnly(BaseModel):
    last_names_or_organization_names: list[str]

def resolve_user_request(user_message: str):

    structured_model = model.with_structured_output(UserRequestInfo, method="json_schema")

    response = structured_model.invoke(
        f"""
        You prepare the user promt to find sanctioned people and/or organizations. Divide all names in single words. Generate possible misspellings.
        Take the user prompt, extract the data in provided structure. You might have to generate names that user is looking forward to search for.
        If user says "sanction by Country" - do not include that country in the countries list

        Do not include human's First Names in names_to_earch_for.
        Do not include any special characters (especially ')
        Do not include any common words describing categories of things like 'bank'
        ---
        User Prompt:
        {user_message}
        """
    )

    unique_names = list({
        word
        for entry in response.names_to_search_for
        for word in entry.split()
    })
    country_codes = country_converter.convert(response.countries, to='ISO2')

    clearing_pass = model.with_structured_output(LastNamesOrOrganizationsOnly, method="json_schema")

    check_res = clearing_pass.invoke(
        f"""
        Please remove any human First Names, leaving anything else in the resulting list
        {unique_names}
        """
    )

    
    filtered_names = [item for item in check_res.last_names_or_organization_names if item not in response.first_names]
    for i in range(len(filtered_names)):
        filtered_names[i] = re.sub(r"[^A-Za-z ]", "", filtered_names[i])

    response.names_to_search_for = filtered_names
    response.countries = country_codes
    
    return response

class NamesModel(BaseModel):
    names: list[str]=Field(description="All names User requested to look for")

def resolve_names(original_request: str):
    names_model = model.with_structured_output(NamesModel, method="json_schema")
    response = names_model.invoke(
        f"""
        Look for all names user requested about. Fill them into names_model
        ---
        User's request:
        {original_request}
        """)
    return response.names


class MisspellingsList(BaseModel):
    all_possible_names_misspellings: list[str]=Field(description="Last Names only. List of strings with all possible name variations given the user can misspell the name")
    first_names: list[str]=Field(description="All human first names made when making misspellings array")
    originnaly_typed_name: str=Field(description="Original name how user typed it")

def resolve_misspellings(original_request: str):

    misspellings_model = model.with_structured_output(MisspellingsList, method="json_schema")
    response = misspellings_model.invoke(
        f"""
        Divide all names in single words. Generate possible misspellings.
        Take the user prompt, extract the data in provided structure. You might have to generate names that user is looking forward to search for.
        If user says "sanction by Country" - do not include that country in the countries list

        Do not include human's First Names in names_to_earch_for.
        Do not include any special characters (especially ')
        Do not include any common words describing categories of things like 'bank'
        Make sure to include original Last Name or Organization name that user provided.
        ---
        User Prompt:
        {original_request}
        """
    )

    response.all_possible_names_misspellings.append(response.originnaly_typed_name)
    unique_names = list({
        word
        for entry in response.all_possible_names_misspellings
        for word in entry.split()
    })

    names = [item for item in unique_names if item not in response.first_names]
    for i in range(len(names)):
        names[i] = re.sub(r"[^A-Za-z ]", "", names[i])
    
    return names


def analyze_request(original_request: str, table_result: DataFrame):
    print("BEGIN REQUEST ANALYZE -- " + original_request)
    df, within_limit = resolve_db_result(table_result)
    table_result = df
    if not within_limit:
        response = model.invoke(
            f"""
            Take the original request and call the tool with the exact name how user called it.
            Provide the total amount of found results, it can be taken as last index of given truncated result. Also provide summary of results.
            ---
            Original Request:
            {original_request}
            ---
            Truncated Result:
            {table_result}
            """
        )
        print("RESPONCE ANALYZED ON SMALL DATA\n")
        return response

    misspellings_model = model.with_structured_output(MisspellingsList, method="json_schema")

    print("NAME VARS CHECK -- ")
    response = misspellings_model.invoke(
        f"""
        Prepare the list of possible name variations that user provided. User could misspell the name, so make possible name variations.
        ---
        User Prompt:
        {original_request}
        """
    )

    print("MAKING BIG RESPONCE....")
    analyzed_responce = model.invoke(
        f"""
        Take this table result and find any entries that user might be looking for, given the original request. Account for possible misspellings.
        If no entries were found - suggest user try to search for affiliated organizations, in case if target is not in sanctions list directly, but can be tied
        to an organization within instead
        ---
        Name variations to look for:
        {response.all_possible_names_misspellings}
        ---
        Original Request:
        {original_request}
        ---
        Table Result:
        {table_result}
        """)

    print("RESPONCE ANALYZED ON BIG DATA\n")
    return analyzed_responce

@tool
def get_column_names():
    """
    Returns all columns in the dataset in case if its unclear what exact type of data user wants
    """
    csv_result = db.execute(f""" 
            SELECT *
            FROM read_csv_auto('data.csv', parallel = false)
            LIMIT 1
         """).fetch_df()
    return csv_result.columns.tolist()

def get_names_query(names:list[str]):
    names_query = ""

    names_query = f"name ILIKE '%{names[0]}%' OR aliases ILIKE '%{names[0]}%'"
    for name in names[1:]:
        names_query += " OR "
        names_query += f"name ILIKE '%{name}%' OR aliases ILIKE '%{name}%'"


    print(f"\n\nQUERY: {names_query}\n\n")
    return names_query 

def get_countries_query(country_codes:list[str]):

    country_query = ""
    if len(country_codes) == 1:
        country_query = f"AND countries LIKE '%{country_codes.lower()}%'"
    else:
        #country_query = f"AND countries IN ({','.join([f"'{c}'" for c in country_codes])})"
        country_query = f"AND (countries LIKE '%{country_codes[0].lower()}%'"
        for country_code in country_codes:
            country_query += " OR "
            country_query += f"countries LIKE '%{country_code.lower()}%'"
        country_query += ")"

    return country_query 

@tool
def find_all_of_names(names:list[str], original_request: str):
    """
    Analyzes the table for all entries for given names or aliases. If anything is found in table - looks for closest match to the requested names and returns the summary back
    """
    originals = names
    names = resolve_misspellings(original_request=original_request)
    names += originals
    names_query = get_names_query(names)

    print("QUERY START...")
    csv_result = db.execute( f"""
            SELECT *
            FROM read_csv_auto('data.csv', parallel = false)
            WHERE {names_query}
        """).fetchdf()
    print("QUERY FINISHED")    

    analyzed_responce = analyze_request(original_request=original_request, table_result=csv_result)
    return analyzed_responce

@tool
def find_all_of_names_and_countries(names:list[str], country_names:list[str], original_request: str):
    """
    Takes: names - list of single word strings; country_names - list of single word strings
    Returns table for all entries for given names or aliases with the specific countries specified
    """
    originals = names
    names = resolve_misspellings(original_request=original_request)
    names += originals
    country_codes = country_converter.convert(country_names, to='ISO2')
    
    country_query = get_countries_query(country_codes)
    names_query = get_names_query(names)

    print("QUERY START...")
    csv_result = db.execute( f"""
            SELECT *
            FROM read_csv_auto('data.csv', parallel = false)
            WHERE {names_query}
            {country_query}
        """).fetchdf()
    print("QUERY FINISHED")

    analyzed_responce = analyze_request(original_request=original_request, table_result=csv_result)
    return analyzed_responce

@tool
def find_all_of_organization_and_countries(orgs:list[str], country_names:list[str], original_request: str):
    """
    Returns table for all entries for given names or aliases of organizations with the specific countries specified
    """
    originals = orgs
    orgs = resolve_misspellings(original_request=original_request)
    orgs += originals
    country_codes = country_converter.convert(country_names, to='ISO2')
        
    orgs_query = get_names_query(orgs)
    country_query = get_countries_query(country_codes)

    print("QUERY START...")
    csv_result = db.execute( f"""
            SELECT *
            FROM read_csv_auto('data.csv', parallel = false)
            WHERE {orgs_query}
            {country_query}
            AND schema = 'Organization'
        """).fetchdf()
    print("QUERY FINISHED")
    
    analyzed_responce = analyze_request(original_request=original_request, table_result=csv_result)
    return analyzed_responce

@tool
def find_all_wildcards_from_column(wildcards:list[str], column:str, original_request: str):
    """
    If calling other tools to find data does not makes sense - use this.
    Returns table given the provided valid column name and wildcard values as whatever needs to be find under that column
    """
    wildcard_query = ""
    if(len(wildcards) == 1):
        wildcard_query = f"{column} ILIKE '%{wildcards}%'"
    else:
        wildcard_query = f"{column} ILIKE '%{wildcards[0]}%'"
        for wildcard in wildcards:
            wildcard_query += f" OR "
            wildcard_query = f"{column} ILIKE '%{wildcard}%'"

    print("QUERY START...")
    csv_result = db.execute( f""" 
        SELECT *
        FROM read_csv_auto('data.csv', parallel = false)
        WHERE {wildcard_query}
    """).fetchdf()
    print("QUERY START...")

    analyzed_responce = analyze_request(original_request=original_request, table_result=csv_result)
    return analyzed_responce

user_requests_history = []
responces_history = []

MAX_MEMORY_SIZE = 20
def add_to_hisotry(user_request: str, agent_responce: str):
    global user_requests_history
    global responces_history
    user_requests_history.append(user_request)
    responces_history.append(agent_responce)
    user_requests_history = user_requests_history[-MAX_MEMORY_SIZE:]
    responces_history = responces_history[-MAX_MEMORY_SIZE:]

def build_queries(last_names):
    queries = []
    
    for name in last_names:
        queries.append(f'"{name}" worked for employment history affiliated with organization board member CEO')
        queries.append(f'"{name}" LinkedIn')
        queries.append(f'"{name}" Headhunter hh.ru')
        queries.append(f'"{name}" работал устроен клиент заказчик начальник директор управляющий руководитель')
    
    return queries

class OrganizationsLookupInfo(BaseModel):
    organization_names: list[str]=Field(description="List of organizations that people with given surnames might be connected to.")

@tool
def search_web_for_connections(original_request: str):
    """
    Searches the web for possible connections of the person or organization who user mentioned to different organizations, workplaces or directors or owners.
    """
    print("trying web_search!")
    names = resolve_names(original_request)
    queries = build_queries(names)
    results_text = ""
    
    for q in queries:
        results = tavily_search.invoke(q)
        for r in results['results']:
            results_text += f"{r['title']}\n{r['content'][:15000]}\n{r['url']}\n\n"

    print(f"WEB SEARCH RESULTS LEN: {len(results_text)}")
    structured_req = model.with_structured_output(OrganizationsLookupInfo, method="json_schema")
    print("INVOKING...")
    data_lookup = structured_req.invoke(
        f"""
        You are tasked to find possible affiliations of given people last names with various organizations in given Web Search Result. 
        You should look specifically if person might've worked in the company or was it's client or did any service for that company.
        Put names of found companies in organization_names list
        ---
        Target People Last Names:
        {str(names)}
        ---
        Web Search Result:
        {results_text}
        """)
    
    print("GOR ORGS: " + str(data_lookup.organization_names))
    return data_lookup

@tool
def check_history(current_user_request: str):
    """
    Figure out whether the current user's request is based on the history of previous messages
    If user requests based solely on the history of his requests and your responces - analyze them and provide a responce.
    If user request seems not connected - proceed to further calling of other tools.
    """

    global user_requests_history
    global responces_history
    response = model.invoke(
        f"""
        Figure out if current user request is based upon the history of interaction. Is it based solely on the history? Or it seems not connected?
        ---
        Current User Request:
        {current_user_request}
        ---
        History of User Requests:
        {str(user_requests_history)}
        ---
        History of your responces:
        {str(responces_history)}
        """
    )
    return response

@tool
def call_news_api(user_request: str):
    """
    If user requested for news - call news api with his request
    """
    return news_api_caller.get_news(mediastack, mediastack_key, user_request)

# Augment the LLM with tools
tools = [check_history, call_news_api, get_column_names, find_all_of_names, find_all_of_names_and_countries, find_all_wildcards_from_column, find_all_of_organization_and_countries, search_web_for_connections]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)

################################################################

# Define Agent State
from langchain_core.messages import ToolMessage
from typing import Literal
from langgraph.graph import StateGraph, START, END

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int

def llm_call(state: dict):
    """LLM decides whether to call a tool or not"""
    
    structured_user_request = resolve_user_request(state['messages'])
    print("------ STRUCTUED USER REQUEST -----------")
    print(structured_user_request)
    print("-------------------------")
    return {
        "messages": [
            model_with_tools.invoke(
                [
                    SystemMessage(
                        content=
                        f"""
                        You are a helpful assistant tasked with looking up the information in imposed political and economical sanctions dataset.
                        Given the structured user request trigger the right collection of tools and provide a summary of data that you recieved from the tools triggered.

                        ----
                        Structured User Request:
                        {structured_user_request}
                        """
                    )
                ]
                + state["messages"]
            )
        ],
        "llm_calls": state.get('llm_calls', 0) + 1
    }


def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"

    # Otherwise, we stop (reply to the user)
    return END

# Build workflow
agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()

#######################################################################

# Show the agent
from IPython.display import Image, display
display(Image(agent.get_graph(xray=True).draw_mermaid_png()))

# Invoke
from langchain_core.messages import HumanMessage, AIMessage

print("GOT TO LOOP")

import gradio as gr

def generate_responce(user_input, history):
    messages = [HumanMessage(content=user_input)]
    try:
        res = agent.invoke({"messages": messages})
        print(res)
        for m in reversed(res["messages"]):
            if isinstance(m, AIMessage):
                add_to_hisotry(user_request=user_input, agent_responce=m.content)
                return m.content
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        line_number = exc_tb.tb_lineno
        res = f"ERROR:{e}\nLine: {line_number}\n{type(e).__name__}\n\n---\n An error occured, please try again!"
        traceback.print_exc()
        return res

gr.ChatInterface(
    fn=generate_responce, 
).queue().launch(server_name="0.0.0.0", share=True)

exit(0)

# The loop will continue indefinitely until explicitly told to stop
while True:
    user_input = input("Enter something (type 'quit' to exit): ")
    if user_input.lower() == 'quit':
        print("Loop exited.")
        break # Exit the loop if the user types 'quit'
    else:
        messages = [HumanMessage(content=user_input)]
        try:
            messages = agent.invoke({"messages": messages})
            for m in messages["messages"]:
                m.pretty_print()
                add_to_hisotry(user_request=user_input, agent_responce=m)
        except Exception as e:
            res = f"ERROR:{e}\n\n---\n An error occured, please try again!"
            print(res)
           
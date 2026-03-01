import os
from dotenv import load_dotenv
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
print(BASE_DIR)
load_dotenv(BASE_DIR / "assignment_2\\.secrets")
openai_key = os.getenv('API_GATEWAY_KEY')

from openai import OpenAI
import urllib.parse

openai_key = os.getenv('API_GATEWAY_KEY')
openai_client = OpenAI(base_url='https://k7uffyg03f.execute-api.us-east-1.amazonaws.com/prod/openai/v1',
                api_key='any value',
                default_headers={"x-api-key": openai_key})


categories = ["general", "business", "entertainment", "health", "science", "sports", "technology"]
country_codes = ["Argentina: ar", "Australia: au", "at", "be", "br", "bg", "ca", "cn", "co", "cz", "eg", "fr", "de", "gr", "hk", "hu", "in", "id",
            "ie", "il", "it", "jp", "lv", "lt", "my", "mx", "ma", "nl", "nz", "ng", "no", "ph", "pl", "pt",
            "ro", "sa", "rs", "sg", "sk", "si", "za", "kr", "se", "ch", "tw", "th", "tr", "ae", "Ukraine: ua", "gb", "us", "ve", "Russia: ru"]
keywords = ["war", "frontline", "peace", "sanctions"]


from pydantic import BaseModel, Field
class RequestInfo(BaseModel):
    countries: list[str]=Field(description=f"Use lowercase. A selection of short country codes of countries that user mentioned. Each country code data in source has format <CountryName>:<country-code>. Extract only two letters per country mentioned. Source is here: {country_codes}")
    keywords: list[str]=Field(description=f"Use lowercase. Extract single word keywords from user's speech if asked for anything specific.")
    limit: int=Field(description="A limit to the news collection. If user did not mention the limit, set it to 10")
    categories: list[str]=Field(description=f"Choose topic from {categories}. If user did not mention anything specific, add all")


print("///SETUP DONE, PROGRAM START///")
print("///////////////////////////////")

def get_news(mediastack, mediastack_key, userPrompt):
    response = openai_client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": "Extract the information from the user's input given the text_format"},
            {
                "role": "user",
                "content": userPrompt,
            },
        ],
        text_format=RequestInfo,
    )

    structuredOutput = response.output_parsed
    print(structuredOutput)

    # Make LLM figure out what user wants and compose a HTTP request to mediastack
    # Beyond this point LLM should figure out: 
    # - categories
    # - countries of news
    # - keywords
    # - languages (english by default)
    # - limit
    # - date/date range

    str_countries = ""
    for country_code in structuredOutput.countries:
        str_countries += country_code
        str_countries += ','

    if(len(str_countries) > 0):
        str_countries = str_countries[:-1]

    str_categories = ""
    for category in structuredOutput.categories:
        if category in categories:
            str_categories += category
            str_categories += ','

    if(len(str_categories) > 0):
        str_categories = str_categories[:-1]

    print(str_categories)

    str_keywords = ""
    for keyword in structuredOutput.keywords:
        if keyword not in categories:
            str_keywords += keyword
            str_keywords += ','

    if(len(str_keywords) > 0):
        str_keywords = str_keywords[:-1]

    print(str_keywords)

    req_obj = {
        'access_key': mediastack_key,
        'sort': 'published_desc',
        'limit': structuredOutput.limit,
        'languages': 'en'
    }

    if(len(str_categories) > 0):
        req_obj['categories'] = str_categories
    if(len(str_keywords) > 0):
        req_obj['keywords'] = str_keywords
    if(len(str_countries) > 0):
        req_obj['countries'] = str_countries

    print(req_obj)
    params = urllib.parse.urlencode(req_obj)

    mediastack.request('GET', '/v1/news?{}'.format(params))
    res = mediastack.getresponse()
    data = res.read()
    decoded_data = data.decode('unicode_escape')

    print(decoded_data)

    devPrompt = "Given the API responce that contains the news, print out the news titles retrieved from the user prompt with that API responce, provde the summary for each, include links at the end of each summary"
    userPrompt = f"Please give me the summary of the content I got from news API{decoded_data}"

    response = openai_client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": devPrompt},
            {
                "role": "user",
                "content": userPrompt,
            },
        ]
    )

    return response
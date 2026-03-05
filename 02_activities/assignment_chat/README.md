### Welcome to Sanctionist 0.1v
> Your handy chat bot to search the data about sanctioned people and organizations

> Launch agent.py to get the chat Agent running on http://127.0.0.1:7860/

> Agent can look up the names and organizations if they have any relation to the sanctioned entities from OpenSanctions data set
> Agent can also look up the news from Mediastack!

### Installation

> Make sure to run these to install extra dependencies:
uv add duckdb
uv add country-converter

### MAKE SURE TO CREATE .SECRETS FILE IN SAME DIRECTION AS AGENT.PY
> .secrets file has to have the API_GATEWAY_KEY and API_MEDIASTACK_KEY and API_TAVILY_KEY
> For Mediastack you can use mine: db1421584ecce977bcffa1813de30073
# Pokemon Battle Assistant

An LLM-powered Pokemon battle assistant supporting Chinese, Japanese, and English. Features intelligent Q&A, damage calculation, usage statistics, and more.

[中文版](README.md)

## Features

- **Intelligent Q&A**: Query Pokemon data via natural language (base stats, moves, abilities, items, etc.)
- **Damage Calculation**: Full generation damage calculation including Terastallization, weather, terrain, and other complex mechanics
- **Usage Statistics**: Query Pokemon HOME Champions battle usage rankings and popular sets
- **Threshold Search**: Find EV spreads that guarantee KOs or survive specific attacks
- **Web Interface**: Dark/light theme, Chinese/Japanese/English trilingual support
- **Android Client**: Built with .NET MAUI, supports SSE streaming responses

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp api/.env.example api/.env
```

Edit `api/.env` and fill in your LLM API Key:

```env
LLM_TOOL_USE_API_KEY=your_api_key_here
LLM_SUMMARY_API_KEY=your_api_key_here
API_BASE_URL=http://localhost:8000
```

### 3. Start the Server

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The first startup will automatically build the RAG index (about 1 minute). Subsequent startups load from cache.

Visit `http://localhost:8000` for the web interface, or `http://localhost:8000/docs` for API documentation.

## Project Structure

```
├── api/                     # FastAPI backend service
│   ├── main.py              # Main entry point
│   ├── llm_service.py       # LLM Agent Loop core
│   ├── chat_service.py      # Chat service main entry
│   ├── prompt/              # LLM prompts and Tool Schema
│   └── .env.example         # Environment variable template
├── damage_calculator/       # Damage calculator (Python + Node.js)
│   ├── cale/                # NCP calculation engine (forked from nerd-of-now)
│   └── cale_chinese_calculator.py  # Chinese translation layer
├── web/                     # Web interface
│   ├── calc/                # Legacy Chinese calculator
│   └── cale/                # Current calculator (English NCP + Chinese overlay)
├── mobile/                  # .NET MAUI Android client
├── pokemon_data/            # Data directory
│   ├── pokemonData.db       # Main database (~119MB)
│   ├── createTable/         # Table creation scripts
│   └── wiki/                # 52poke Wiki data
│       ├── wiki_meta.db     # Wiki metadata
│       └── wikitext_cache/  # Wiki raw text cache
├── models/                  # Embedding model
│   └── bge-small-zh-v1.5/  # Chinese semantic vector model
└── requirements.txt
```

## Tech Stack

- **Python 3.9+**: Backend service, data processing
- **FastAPI**: API framework
- **SQLite**: Data storage
- **Node.js**: Damage calculation engine
- **BGE Small ZH**: Chinese semantic vector retrieval
- **jieba + pypinyin**: Chinese word segmentation and pinyin matching
- **.NET MAUI**: Android client

## Data Sources

| Source | Purpose | License |
|--------|---------|---------|
| [PokeAPI](https://pokeapi.co/) | Pokemon base data (English) | MIT |
| [52Poke Wiki](https://wiki.52poke.com/) | Chinese wiki data | CC BY-NC-SA 3.0 |
| [NCP VGC Damage Calculator](https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/) | Damage calculation engine | MIT |
| [pokedb.tokyo](https://champs.pokedb.tokyo/) | HOME Champions usage data | - |

See [Credits and License](#credits-and-license) below for details.

## Credits and License

### Project License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

### Third-Party Credits

#### Damage Calculator

The damage calculation feature is forked from [NCP VGC Damage Calculator](https://github.com/nerd-of-now/NCP-VGC-Damage-Calculator/), maintained by nerd-of-now.

> Originally the official Nuggetbridge damage calculator 2015-2016, later adapted for Trainer Tower 2017-2020, now adapted for Nimbasa City Post from 2021-present. Maintained and developed by nerd-of-now.
>
> Credits and license: MIT License.
>
> Written by Honko. VGC 2015 Update by Tapin and Firestorm. VGC 2016, 2017, 2018, 2019, and 2020 done by squirrelboyVGC. VGC 2021 onwards done by nerd-of-now.

#### 52Poke Wiki

This project downloaded encyclopedia content (battle terminology, move effects, terrain/weather descriptions, etc.) from [52Poke Wiki](https://wiki.52poke.com/) via its MediaWiki API, stored in a database for RAG retrieval.

Per its license:
- **Attribution (BY)**: Data sourced from [52Poke Wiki](https://wiki.52poke.com/), contributed by 52Poke Wiki editors
- **Non-Commercial (NC)**: This project is for personal learning and non-commercial use only
- **ShareAlike (SA)**: Derivative works based on 52Poke content are also subject to [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/deed.en)

#### HOME Champions Usage Data

The usage statistics feature uses Pokemon HOME Champions battle usage data provided by [champs.pokedb.tokyo](https://champs.pokedb.tokyo/), organized and maintained by the pokedb.tokyo team.

#### PokeAPI

Base Pokemon data comes from [PokeAPI](https://pokeapi.co/), an open Pokemon RESTful API.

#### jQuery

The web interface uses [jQuery](https://jquery.com/) (MIT License):
- jQuery 3.1.1 (`web/calc/jquery-3.1.1.min.js`)
- jQuery 2.1.0 (`web/calc/script_res/jquery-2.1.0.min.js`)

#### select2

The web interface uses [select2](https://select2.org/) (Apache License 2.0 or GNU GPL v2.0 dual license):
- `web/calc/script_res/select2.min.js`

#### Embedding Model

Semantic vector retrieval uses [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5) (MIT License).

#### Pokemon Copyright

Pokemon and its related names, images, data, and other intellectual property are owned by Nintendo / Creatures Inc. / GAME FREAK inc. This project is an unofficial fan project with no affiliation, authorization, or endorsement from the aforementioned companies, and is for learning and exchange purposes only.

The Pokemon images used in this project are sourced from [PokeAPI](https://pokeapi.co/) and are used solely under the principle of Fair Use for non-commercial explanation and display purposes.

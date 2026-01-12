# <img src="https://raw.githubusercontent.com/warmo1/eonha/main/images/logo.png" width="50" height="50" alt="E.ON Next Logo"> E.ON Home Assistant Integration

![Version](https://img.shields.io/badge/version-v1.1.0-blue)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

This project aims to integrate E.ON Next API data into Home Assistant.
It currently includes the `eonapi` library and scripts to verify connection.

## Setup

1.  Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2.  Install dependencies:
    ```bash
    pip install -e ./eonapi
    pip install pytest pytest-asyncio
    ```

## Testing

Run unit tests (no credentials needed):
```bash
pytest tests/
```

Run connection test (requires credentials):
```bash
export EON_USERNAME="your-email"
export EON_PASSWORD="your-password"
python check_connection.py
```

## Structure
- `eonapi/`: Submodule containing the API client library.
- `tests/`: Unit tests.
- `check_connection.py`: Script to verify API access.

## Installation
See [INSTALL.md](INSTALL.md) for installation instructions.

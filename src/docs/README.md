# Site System Storage

## Overview
This system is designed to save and manage website content and system information. It provides functionality for scraping websites, storing their content, and collecting system metrics.

## Features
- Website content scraping and storage
- System information collection and monitoring
- Multi-language support
- Configurable logging
- File management utilities

## Installation
1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage
To run the application:
```bash
python -m src.app.main
```

## Configuration
Configuration can be modified in `src/config/settings.py`. Key settings include:
- Logging configuration
- Scraping parameters
- Backup settings
- Directory paths

## Project Structure
```
src/
├── app/           # Core application code
├── config/        # Configuration files
├── docker/        # Docker configuration
├── docs/          # Documentation
├── locales/       # Internationalization files
├── tests/         # Test files
└── utils/         # Utility modules
```

## Development
- Use Python 3.8 or higher
- Follow PEP 8 style guidelines
- Write tests for new features
- Update documentation as needed

## Testing
Run tests using:
```bash
pytest src/tests/
```

## License
MIT License

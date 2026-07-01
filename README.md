# Yeastar S-Series Toolkit

Lightweight web-based management tool for Yeastar S-Series PBX using the official API v2.0.

The application allows administrators to browse extensions, edit extension settings, and perform bulk updates using CSV files through a simple web interface.

No external HTML templates are required. The web interface is generated directly by the application.

---

## Features

- Extension Dashboard
- View Extension Details
- Edit Extension Settings
- Bulk Update from CSV
- No Answer Forward
- Busy Forward
- Ring Timeout
- Custom Number Forwarding
- CSV Preview
- CSV Template Generator
- HTTP Session Reuse
- Token Cache
- API v2.0 Support

---

## Requirements

- Python 3.9+
- Flask
- Requests

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a configuration file named `config.ini`.

Example:

```ini
[yeastar]
host=192.168.1.10
https=false
username=admin
password=your_password
```

---

## Run

```bash
python3 app.py
```

Open your browser:

```
http://localhost:5000
```

---

## Bulk Update

The application can automatically generate a CSV template.

Supported operations include:

- No Answer Forward
- Busy Forward
- Ring Timeout
- Custom Number Forwarding
- Extension Settings

Always use **Test Mode** before applying changes to all extensions.

---

## Compatibility

Developed and tested with:

- Yeastar S-Series PBX
- API v2.0

---

## License

MIT License

---

## Disclaimer

This project is not affiliated with or endorsed by Yeastar.

Always create a PBX backup before performing bulk configuration changes.

Use this software at your own risk.

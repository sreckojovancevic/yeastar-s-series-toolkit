#!/usr/bin/env python3
"""
Yeastar Extension Manager - Full Version with BusyForward Bulk Fix
"""

import hashlib
import configparser
import csv
import io
import json
import time
from flask import Flask, render_template_string, request, jsonify
import requests

app = Flask(__name__)
app.secret_key = 'yeastar-secret-key-change-this'

# ============================================================
# KONFIGURACIJA
# ============================================================

cfg = configparser.ConfigParser()
cfg.read("config.ini")

HOST = cfg["yeastar"]["host"].strip()
HTTPS = cfg["yeastar"].getboolean("https", fallback=False)
USERNAME = cfg["yeastar"]["username"].strip()
PASSWORD = cfg["yeastar"]["password"].strip()

PROTOCOL = "https" if HTTPS else "http"
PASSWORD_MD5 = hashlib.md5(PASSWORD.encode("utf-8")).hexdigest()

# Korišćenje Session objekta za HTTP Keep-Alive
session_http = requests.Session()

# ============================================================
# TOKEN CACHE
# ============================================================

_token_cache = {
    "token": None,
    "expires": 0
}

def get_token():
    """Dobija token, koristi keš ako je validan"""
    if _token_cache.get("token") and time.time() < _token_cache.get("expires", 0):
        return _token_cache["token"]

    url = f"{PROTOCOL}://{HOST}/api/v2.0.0/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD_MD5,
        "port": "8260",
        "version": "2.0.0"
    }

    try:
        resp = session_http.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "Success":
            raise Exception(f"Login failed: {data}")

        _token_cache["token"] = data["token"]
        _token_cache["expires"] = time.time() + 25 * 60
        return _token_cache["token"]
    except Exception as e:
        _token_cache["token"] = None
        _token_cache["expires"] = 0
        raise Exception(f"Neuspešna autentifikacija na Yeastar: {e}")

def api_request(endpoint, payload=None):
    """Izvršava API zahteve sa proverom grešaka"""
    try:
        token = get_token()
        url = f"{PROTOCOL}://{HOST}/api/v2.0.0/{endpoint}?token={token}"
        resp = session_http.post(url, json=payload, timeout=5)
        resp.raise_for_status()

        res_json = resp.json()
        
        # Provera isteka tokena
        if res_json.get("status") == "Failed" and res_json.get("errno") in ["10001", "10002"]:
            _token_cache["token"] = None
            _token_cache["expires"] = 0
            token = get_token()
            url = f"{PROTOCOL}://{HOST}/api/v2.0.0/{endpoint}?token={token}"
            resp = session_http.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            res_json = resp.json()

        if res_json.get("status") == "Failed":
            raise Exception(f"API Error {res_json.get('errno', 'unknown')} (Vraćen JSON: {res_json})")

        return res_json
    except Exception as e:
        raise Exception(f"Greška u komunikaciji sa centralom: {e}")

# ============================================================
# HTML TEMPLATE
# ============================================================

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Yeastar Extension Manager</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: white; border-radius: 12px; padding: 20px 30px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .header h1 { color: #1a73e8; margin: 0; }
        .header .status { font-size: 14px; color: #666; }
        .header .status .online { color: #4caf50; font-weight: bold; }
        .tabs { display: flex; gap: 5px; margin-bottom: 20px; background: white; border-radius: 12px; padding: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); flex-wrap: wrap; }
        .tab { padding: 12px 24px; border: none; background: transparent; cursor: pointer; border-radius: 8px; font-size: 15px; font-weight: 600; color: #666; transition: all 0.3s; }
        .tab:hover { background: #e8f0fe; color: #1a73e8; }
        .tab.active { background: #1a73e8; color: white; }
        .content { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .search-box input { flex: 1; padding: 10px 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px; min-width: 200px; }
        .search-box input:focus { border-color: #1a73e8; outline: none; }
        .search-box button { padding: 10px 20px; background: #1a73e8; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .search-box button:hover { background: #1557b0; }
        .search-box button.green { background: #28a745; }
        .search-box button.green:hover { background: #1e7e34; }
        .ext-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; max-height: 500px; overflow-y: auto; padding: 5px; }
        .ext-card { background: #f8f9fa; padding: 15px 10px; border-radius: 8px; text-align: center; cursor: pointer; border: 2px solid transparent; transition: all 0.2s; }
        .ext-card:hover { border-color: #1a73e8; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(26,115,232,0.2); }
        .ext-card .number { font-size: 20px; font-weight: bold; color: #1a73e8; }
        .ext-card .name { font-size: 12px; color: #666; margin-top: 5px; word-break: break-all; }
        .ext-card .status-badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 10px; font-weight: 600; margin-top: 5px; }
        .status-badge.registered { background: #4caf50; color: white; }
        .status-badge.unavailable { background: #f44336; color: white; }
        .status-badge.idle { background: #ffc107; color: #333; }
        .status-badge.busy { background: #ff9800; color: white; }
        .status-badge.ringing { background: #2196f3; color: white; }
        .detail-panel { background: #f8f9fa; border-radius: 8px; padding: 20px; margin-top: 20px; display: none; }
        .detail-panel.show { display: block; }
        .detail-panel h3 { margin-top: 0; color: #1a73e8; display: flex; justify-content: space-between; align-items: center; }
        .close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }
        .close-btn:hover { color: #f44336; }
        .detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
        .detail-item { background: white; padding: 12px 15px; border-radius: 6px; border-left: 4px solid #1a73e8; }
        .detail-item label { font-size: 11px; color: #999; text-transform: uppercase; font-weight: 600; display: block; margin-bottom: 2px; }
        .detail-item .value { font-size: 15px; font-weight: 500; }
        .detail-item input, .detail-item select { width: 100%; padding: 6px 10px; border: 2px solid #ddd; border-radius: 4px; font-size: 14px; margin-top: 2px; }
        .detail-item input:focus, .detail-item select:focus { border-color: #1a73e8; outline: none; }
        .save-btn { padding: 10px 30px; background: #4caf50; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; margin-top: 15px; }
        .save-btn:hover { background: #388e3c; }
        .save-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .bulk-area { border: 2px dashed #ddd; border-radius: 8px; padding: 30px; text-align: center; margin: 20px 0; }
        .bulk-area.dragover { border-color: #1a73e8; background: #e8f0fe; }
        .bulk-area input[type="file"] { margin: 10px 0; }
        .csv-preview { background: #f5f5f5; padding: 15px; border-radius: 6px; max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 13px; margin: 10px 0; white-space: pre; }
        .log-area { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 6px; max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 13px; white-space: pre-wrap; margin: 10px 0; }
        .log-area .ok { color: #4caf50; }
        .log-area .error { color: #f44336; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 15px 0; }
        .stat-box { background: white; padding: 15px; border-radius: 6px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
        .stat-box .number { font-size: 28px; font-weight: bold; }
        .stat-box.success .number { color: #4caf50; }
        .stat-box.failed .number { color: #f44336; }
        .stat-box.total .number { color: #1a73e8; }
        .spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #1a73e8; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .hidden { display: none; }
        .toast { position: fixed; bottom: 20px; right: 20px; padding: 15px 25px; border-radius: 8px; color: white; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.3); animation: slideIn 0.3s ease; display: none; z-index: 999; }
        .toast.success { background: #4caf50; }
        .toast.error { background: #f44336; }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        .loading-placeholder { text-align: center; padding: 40px; color: #999; grid-column: 1/-1; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>☎️ Extension Manager</h1>
            <div class="status">
                <span class="online">● Online</span>
                <span style="margin-left:15px;" id="hostDisplay" data-host="{{ host }}">{{ host }}</span>
                <button onclick="loadExtensions()" style="margin-left:15px;padding:6px 15px;background:#1a73e8;color:white;border:none;border-radius:4px;cursor:pointer;">🔄 Refresh</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="dashboard">📊 Dashboard</button>
            <button class="tab" data-tab="bulk">📦 Bulk Update</button>
        </div>

        <div class="content">
            <div id="tab-dashboard" class="tab-content active">
                <div class="search-box">
                    <input type="text" id="searchInput" placeholder="🔍 Pretraži ekstenzije..." oninput="filterExtensions()">
                    <button onclick="filterExtensions()">🔍 Pretraži</button>
                    <button class="green" onclick="loadExtensions()">🔄 Učitaj</button>
                </div>
                <div id="extensionGrid" class="ext-grid">
                    <div class="loading-placeholder"><span class="spinner"></span> Učitavanje...</div>
                </div>

                <div id="detailPanel" class="detail-panel">
                    <h3>
                        <span id="detailTitle">✏️ Ekstenzija</span>
                        <button class="close-btn" onclick="closeDetail()">×</button>
                    </h3>
                    <div id="detailContent" class="detail-grid"></div>
                    <button class="save-btn" id="saveExtBtn" onclick="saveExtension()">💾 Sačuvaj</button>
                    <span id="saveStatus" style="margin-left:15px;font-size:14px;"></span>
                </div>
            </div>

            <div id="tab-bulk" class="tab-content">
                <h3>📦 Bulk Update Ekstenzija</h3>
                <div class="bulk-area" id="dropZone">
                    <p style="font-size:16px;font-weight:600;">📁 Prevucite CSV fajl ovde</p>
                    <p>ili</p>
                    <input type="file" id="bulkFile" accept=".csv">
                    <br><br>
                    <label><input type="checkbox" id="bulkTestMode" checked> <strong>Test mode</strong> (samo prvi red)</label>
                    <br><br>
                    <button class="save-btn" onclick="uploadBulk()">🚀 Pokreni bulk update</button>
                    <button class="save-btn" onclick="downloadTemplate()" style="background:#ffc107;color:#333;">📥 Template</button>
                    <button class="save-btn" onclick="previewBulk()" style="background:#2196f3;">👁️ Preview</button>
                </div>

                <div id="bulkPreview" class="hidden">
                    <h4>📄 Preview CSV</h4>
                    <div id="bulkPreviewContent" class="csv-preview"></div>
                </div>

                <div id="bulkResults" class="hidden">
                    <h4>📊 Rezultati</h4>
                    <div class="stats">
                        <div class="stat-box success"><div class="number" id="bulkSuccess">0</div>✅ Uspešno</div>
                        <div class="stat-box failed"><div class="number" id="bulkFailed">0</div>❌ Neuspešno</div>
                        <div class="stat-box total"><div class="number" id="bulkTotal">0</div>📊 Ukupno</div>
                    </div>
                    <div id="bulkLog" class="log-area"></div>
                </div>
            </div>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    {% raw %}
    <script>
        let extensions = [];
        let selectedExt = null;

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                document.getElementById('tab-' + this.dataset.tab).classList.add('active');
            });
        });

        function loadExtensions() {
            const grid = document.getElementById('extensionGrid');
            grid.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Učitavanje...</div>';

            fetch('/api/extensions')
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        grid.innerHTML = `<div class="loading-placeholder" style="color:#f44336;">❌ ${data.error}</div>`;
                        return;
                    }
                    extensions = data.extlist || [];
                    renderExtensions(extensions);
                })
                .catch(err => {
                    grid.innerHTML = `<div class="loading-placeholder" style="color:#f44336;">❌ Greška: ${err.message}</div>`;
                });
        }

        function renderExtensions(list) {
            const grid = document.getElementById('extensionGrid');
            if (!list || !list.length) {
                grid.innerHTML = '<div class="loading-placeholder">📭 Nema ekstenzija</div>';
                return;
            }

            let htmlString = '';
            for (let i = 0; i < list.length; i++) {
                let ext = list[i];
                let status = ext.status || 'Unknown';
                htmlString += `
                    <div class="ext-card" onclick="showDetail('${ext.number}')">
                        <div class="number">${ext.number}</div>
                        <div class="name">${ext.username || ext.number}</div>
                        <span class="status-badge ${status.toLowerCase()}">${status}</span>
                    </div>
                `;
            }
            grid.innerHTML = htmlString;
        }

        function filterExtensions() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtered = extensions.filter(ext =>
                ext.number.includes(query) ||
                (ext.username && ext.username.toLowerCase().includes(query))
            );
            renderExtensions(filtered);
        }

        function showDetail(extNumber) {
            selectedExt = extNumber;
            document.getElementById('detailPanel').classList.add('show');
            document.getElementById('detailTitle').textContent = `✏️ Ekstenzija ${extNumber}`;
            document.getElementById('saveStatus').textContent = '';
            document.getElementById('saveExtBtn').disabled = true;

            fetch(`/api/extension/${extNumber}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('detailContent').innerHTML = `<div style="color:#f44336;">❌ ${data.error}</div>`;
                        return;
                    }
                    renderDetail(data);
                    document.getElementById('saveExtBtn').disabled = false;
                })
                .catch(err => {
                    document.getElementById('detailContent').innerHTML = `<div style="color:#f44336;">❌ Greška: ${err.message}</div>`;
                });
        }

        function filterExtensions() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const filtered = extensions.filter(ext =>
                ext.number.includes(query) ||
                (ext.username && ext.username.toLowerCase().includes(query))
            );
            renderExtensions(filtered);
        }

        function showDetail(extNumber) {
            selectedExt = extNumber;
            document.getElementById('detailPanel').classList.add('show');
            document.getElementById('detailTitle').textContent = `✏️ Ekstenzija ${extNumber}`;
            document.getElementById('saveStatus').textContent = '';
            document.getElementById('saveExtBtn').disabled = true;

            fetch(`/api/extension/${extNumber}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('detailContent').innerHTML = `<div style="color:#f44336;">❌ ${data.error}</div>`;
                        return;
                    }
                    renderDetail(data);
                    document.getElementById('saveExtBtn').disabled = false;
                })
                .catch(err => {
                    document.getElementById('detailContent').innerHTML = `<div style="color:#f44336;">❌ Greška: ${err.message}</div>`;
                });
        }

        function renderDetail(data) {
            const ext = data.extinfos ? data.extinfos[0] : data;
            const fields = [
                { key: 'number', label: '📞 Broj', editable: false },
                { key: 'username', label: '👤 Ime', editable: true },
                { key: 'status', label: '📊 Status', editable: false },
                { key: 'callerid', label: '📞 Caller ID', editable: true },
                { key: 'email', label: '📧 Email', editable: true },
                { key: 'mobile', label: '📱 Mobilni', editable: true },
                { key: 'hasvoiceemail', label: '📨 Voice mail', editable: true, type: 'select', options: ['on', 'off'] },
                { key: 'alwaysforward', label: '↪️ Uvek preusmeri', editable: true, type: 'select', options: ['on', 'off'] },
                { key: 'noanswerforward', label: '↪️ Preusmeri pri neodgovaranju', editable: true, type: 'select', options: ['on', 'off'] },
                { key: 'busyforward', label: '↪️ Preusmeri pri zauzetosti', editable: true, type: 'select', options: ['on', 'off'] },
                { key: 'ntransferto', label: '🎯 Destinacija (no answer)', editable: true, type: 'select', options: ['Voicemail', 'Extension', 'Mobile Number', 'Custom Number'] },
                { key: 'btransferto', label: '🎯 Destinacija (busy)', editable: true, type: 'select', options: ['Voicemail', 'Extension', 'Mobile Number', 'Custom Number'] },
                { key: 'ntransferprefix', label: '🔢 Prefiks (no answer)', editable: true },
                { key: 'btransferprefix', label: '🔢 Prefiks (busy)', editable: true },
                { key: 'ntransfernum', label: '📞 Broj (no answer)', editable: true },
                { key: 'btransfernum', label: '📞 Broj (busy)', editable: true },
                { key: 'ringtimeout', label: '⏱️ Ring timeout (s)', editable: true },
                { key: 'maxduration', label: '⏱️ Max duration (s)', editable: true },
                { key: 'callrestriction', label: '🔒 Outbound restriction', editable: true, type: 'select', options: ['on', 'off'] },
                { key: 'dnd', label: '🚫 DND', editable: true, type: 'select', options: ['on', 'off'] }
            ];

            let htmlString = '';
            for (let i = 0; i < fields.length; i++) {
                let f = fields[i];
                let value = ext[f.key] !== undefined ? ext[f.key] : '';
                let input = `<div class="value">${value || '-'}</div>`;
                
                if (f.editable) {
                    if (f.type === 'select') {
                        let optionsHtml = '';
                        for (let j = 0; j < f.options.length; j++) {
                            let o = f.options[j];
                            let selected = (o == value) ? 'selected' : '';
                            optionsHtml += `<option value="${o}" ${selected}>${o}</option>`;
                        }
                        input = `<select id="field_${f.key}" data-key="${f.key}">${optionsHtml}</select>`;
                    } else {
                        input = `<input type="text" id="field_${f.key}" data-key="${f.key}" value="${value}">`;
                    }
                }
                htmlString += `<div class="detail-item"><label>${f.label}</label>${input}</div>`;
            }
            document.getElementById('detailContent').innerHTML = htmlString;
        }

        function closeDetail() {
            document.getElementById('detailPanel').classList.remove('show');
            selectedExt = null;
        }

        function saveExtension() {
            if (!selectedExt) return;
            const btn = document.getElementById('saveExtBtn');
            btn.disabled = true;
            document.getElementById('saveStatus').textContent = '⏳ Snimanje...';
            document.getElementById('saveStatus').style.color = '#ff9800';
            const payload = { number: selectedExt };
            
            document.querySelectorAll('#detailContent input, #detailContent select').forEach(el => {
                if (el.dataset.key) {
                    payload[el.dataset.key] = el.value.trim();
                }
            });

            fetch('/api/extension/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'Success') {
                    document.getElementById('saveStatus').textContent = '✅ Sačuvano!';
                    document.getElementById('saveStatus').style.color = '#4caf50';
                    showToast('✅ Sačuvano za ' + selectedExt, 'success');
                    loadExtensions();
                    setTimeout(() => showDetail(selectedExt), 500);
                } else {
                    const errMsg = data.error || data.errno || 'nepoznata greška';
                    document.getElementById('saveStatus').textContent = '❌ Greška: ' + errMsg;
                    document.getElementById('saveStatus').style.color = '#f44336';
                    showToast('❌ Greška: ' + errMsg, 'error');
                }
            })
            .catch(err => {
                document.getElementById('saveStatus').textContent = '❌ ' + err.message;
                document.getElementById('saveStatus').style.color = '#f44336';
                showToast('❌ ' + err.message, 'error');
            })
            .finally(() => {
                btn.disabled = false;
            });
        }

        function downloadTemplate() {
            const headers = 'ext_number,alwaysforward,noanswerforward,busyforward,ntransferto,btransferto,ntransferprefix,btransferprefix,ntransfernum,btransfernum,ringtimeout,maxduration,callrestriction,dnd\\n';
            const sample = '150,off,on,on,Custom Number,Custom Number,64,64,8703312,8703312,10,,off,off';
            const blob = new Blob([headers + sample], {type: 'text/csv'});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'extensions_bulk_template.csv';
            a.click();
            showToast('📥 Šablon preuzet', 'success');
        }

        function previewBulk() {
            const file = document.getElementById('bulkFile').files[0];
            if (!file) { showToast('⚠️ Izaberi CSV', 'error'); return; }
            const formData = new FormData();
            formData.append('file', file);

            fetch('/api/bulk/preview', { method: 'POST', body: formData })
                .then(res => res.json())
                .then(data => {
                    document.getElementById('bulkPreview').classList.remove('hidden');
                    document.getElementById('bulkPreviewContent').textContent = data.preview || data.error;
                });
        }

        function uploadBulk() {
            const file = document.getElementById('bulkFile').files[0];
            if (!file) { showToast('⚠️ Izaberi CSV', 'error'); return; }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('test_mode', document.getElementById('bulkTestMode').checked ? 'true' : 'false');

            document.getElementById('bulkResults').classList.remove('hidden');
            document.getElementById('bulkLog').textContent = '⏳ Obrada u toku...';
            fetch('/api/bulk/upload', { method: 'POST', body: formData })
                .then(res => res.json())
                .then(data => {
                    document.getElementById('bulkLog').textContent = data.log || 'Nema loga';
                    document.getElementById('bulkSuccess').textContent = data.success || 0;
                    document.getElementById('bulkFailed').textContent = data.failed || 0;
                    document.getElementById('bulkTotal').textContent = data.total || 0;
                    showToast('✅ Bulk update završen', 'success');
                    loadExtensions();
                });
        }

        const dropZone = document.getElementById('dropZone');
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('dragover'); });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) document.getElementById('bulkFile').files = e.dataTransfer.files;
        });

        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast ' + type;
            toast.style.display = 'block';
            clearTimeout(toast._timeout);
            toast._timeout = setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        loadExtensions();
    </script>
    {% endraw %}
</body>
</html>
"""

# ============================================================
# FLASK RUTE
# ============================================================

@app.route('/')
def index():
    return render_template_string(HTML, host=HOST)

@app.route('/api/extensions')
def get_extensions():
    try:
        data = api_request('extension/list')
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/extension/<number>')
def get_extension(number):
    try:
        data = api_request('extension/query', {"number": number})
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/extension/update', methods=['POST'])
def update_extension():
    try:
        raw_payload = request.json
        if not raw_payload or 'number' not in raw_payload:
            return jsonify({"status": "Failed", "error": "Nedostaje broj ekstenzije"})

        ext_number = str(raw_payload['number']).strip()

        # ============================================================
        # 1. POZIV: Glavni podaci i Forward pravila (BEZ ringtimeout/maxduration)
        # ============================================================
        main_payload = {
            "number": ext_number
        }

        basic_fields = ['username', 'callerid', 'email', 'mobile', 'hasvoiceemail', 'callrestriction', 'dnd']
        for field in basic_fields:
            if field in raw_payload:
                val = str(raw_payload[field]).strip()
                if val != "":
                    main_payload[field] = val

        if raw_payload.get('noanswerforward') == 'on':
            main_payload['noanswerforward'] = 'on'
            main_payload['ntransferto'] = str(raw_payload.get('ntransferto', 'Voicemail')).strip()
            main_payload['ntransferprefix'] = str(raw_payload.get('ntransferprefix', '')).strip()
            main_payload['ntransfernum'] = str(raw_payload.get('ntransfernum', '')).strip()
        else:
            main_payload['noanswerforward'] = 'off'

        if raw_payload.get('busyforward') == 'on':
            main_payload['busyforward'] = 'on'
            main_payload['btransferto'] = str(raw_payload.get('btransferto', 'Voicemail')).strip()
            main_payload['btransferprefix'] = str(raw_payload.get('btransferprefix', '')).strip()
            main_payload['btransfernum'] = str(raw_payload.get('btransfernum', '')).strip()
        else:
            main_payload['busyforward'] = 'off'

        if raw_payload.get('alwaysforward') == 'on':
            main_payload['alwaysforward'] = 'on'
        else:
            main_payload['alwaysforward'] = 'off'

        print("📥 API UPDATE CALL 1 (Main Data & Forwards)")
        last_response = api_request('extension/update', main_payload)

        # ============================================================
        # 2. POZIV: Vremenska polja
        # ============================================================
        time_payload = {
            "number": ext_number
        }
        has_time_fields = False

        for numeric_key in ['ringtimeout', 'maxduration']:
            if numeric_key in raw_payload:
                val_str = str(raw_payload[numeric_key]).strip()
                if val_str.isdigit():
                    time_payload[numeric_key] = val_str
                    has_time_fields = True

        if has_time_fields:
            print("📥 API UPDATE CALL 2 (Isolated Time Fields)")
            last_response = api_request('extension/update', time_payload)

        return jsonify(last_response)

    except Exception as e:
        print(f"❌ UPDATE EXCEPTION: {e}")
        return jsonify({"error": str(e), "status": "Failed"})

@app.route('/api/bulk/preview', methods=['POST'])
def bulk_preview():
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "Nema fajla"})
        content = file.read().decode('utf-8')
        lines = content.split('\n')
        preview = '\n'.join(lines[:20])
        if len(lines) > 20:
            preview += f'\n... i još {len(lines) - 20} redova'
        return jsonify({"preview": preview})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/bulk/upload', methods=['POST'])
def bulk_upload():
    log_lines = []
    def add_log(msg):
        log_lines.append(msg)

    try:
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "Nema fajla"})

        test_mode = request.form.get('test_mode') == 'true'
        add_log(f"📁 Fajl: {file.filename}")
        add_log(f"🔍 Test mode: {'DA' if test_mode else 'NE'}")

        content = file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        total = len(rows)
        add_log(f"📊 Pronađeno {total} redova")

        if test_mode and rows:
            rows = rows[:1]
            add_log(f"🔍 TEST MODE: izvršavam samo 1. red")

        success = 0
        failed = 0

        for i, row in enumerate(rows, 1):
            ext_num = row.get("ext_number", row.get("extension", row.get("username", ""))).strip()
            if not ext_num:
                add_log(f"⚠️ Red {i}: preskačem (prazan broj ekstenzije)")
                continue

            # --------------------------------------------------------
            # 1. PAKET: Glavni podaci i sva Forward pravila
            # --------------------------------------------------------
            main_payload = {
                "number": ext_num
            }

            is_simplified_on = 'prefix' in row or 'mobile' in row
            mobile_val = row.get('mobile', '').strip() if is_simplified_on else ""

            if is_simplified_on and mobile_val:
                # TVOJ UPROŠĆENI FORMAT (samo prefix i mobile)
                main_payload['noanswerforward'] = 'on'
                main_payload['ntransferto'] = 'Custom Number'
                main_payload['ntransferprefix'] = row.get('prefix', '').strip()
                main_payload['ntransfernum'] = mobile_val
            else:
                # TVOJ KOMPLETAN CSV ŠABLON (1extensions_bulk_ready.csv)
                
                # --- NO ANSWER FORWARD ---
                if 'noanswerforward' in row:
                    nav = row.get('noanswerforward', '').strip().lower()
                    if nav in ['on', 'off']:
                        main_payload['noanswerforward'] = nav
                        if nav == 'on':
                            main_payload['ntransferto'] = row.get('ntransferto', 'Voicemail').strip()
                            main_payload['ntransferprefix'] = row.get('ntransferprefix', '').strip()
                            main_payload['ntransfernum'] = row.get('ntransfernum', '').strip()

                # --- BUSY FORWARD ---
                if 'busyforward' in row:
                    bf = row.get('busyforward', '').strip().lower()
                    if bf in ['on', 'off']:
                        main_payload['busyforward'] = bf
                        if bf == 'on':
                            main_payload['btransferto'] = row.get('btransferto', 'Voicemail').strip()
                            main_payload['btransferprefix'] = row.get('btransferprefix', '').strip()
                            main_payload['btransfernum'] = row.get('btransfernum', '').strip()

                # --- ALWAYS FORWARD ---
                if 'alwaysforward' in row:
                    alw = row.get('alwaysforward', '').strip().lower()
                    if alw in ['on', 'off']:
                        main_payload['alwaysforward'] = alw

            # Preslikavanje ostalih tekstualnih polja ako nisu prazna
            for key in ["username", "fullname", "email", "callrestriction", "dnd"]:
                if row.get(key) and row.get(key).strip() != "":
                    if key == "fullname":
                        main_payload["username"] = row.get(key).strip()
                    else:
                        main_payload[key] = row.get(key).strip()

            # --------------------------------------------------------
            # 2. PAKET: Tajmeri (Ringtimeout / Maxduration)
            # --------------------------------------------------------
            time_payload = {
                "number": ext_num
            }
            has_time = False

            if is_simplified_on and mobile_val:
                rt_val = row.get('ringtimeout', '12').strip()
                time_payload['ringtimeout'] = rt_val if rt_val.isdigit() else '12'
                has_time = True
            else:
                for numeric_key in ['ringtimeout', 'maxduration']:
                    if row.get(numeric_key) and row.get(numeric_key).strip().isdigit():
                        time_payload[numeric_key] = row.get(numeric_key).strip()
                        has_time = True

            # --------------------------------------------------------
            # SLANJE NA CENTRALU
            # --------------------------------------------------------
            try:
                if len(main_payload) > 1:
                    api_request('extension/update', main_payload)
                
                if has_time:
                    api_request('extension/update', time_payload)
                    
                add_log(f"✅ [{i}] Lokal {ext_num} uspešno ažuriran (uneta sva forward pravila)")
                success += 1
            except Exception as e:
                add_log(f"❌ [{i}] Lokal {ext_num} Greška: {e}")
                failed += 1

        add_log(f"\n📊 REZULTAT: ✅ Uspešno: {success} | ❌ Neuspešno: {failed} | 📊 Ukupno: {len(rows)}")

        return jsonify({
            "success": success,
            "failed": failed,
            "total": total,
            "log": "\n".join(log_lines)
        })

    except Exception as e:
        add_log(f"❌ Globalna Greška: {e}")
        return jsonify({
            "error": str(e),
            "log": "\n".join(log_lines)
        })

if __name__ == '__main__':
    print("=" * 60)
    print("☎️ Yeastar Extension Manager (Full Version Active)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)

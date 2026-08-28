#!/usr/bin/env python3
"""Auditoría: llamadas al chatter con HTML en str sin Markup.

Uso (desde la carpeta raíz de Módulos):
    python3 Inventario/stock_lot_dimensions/tools/scan_chatter_html.py

En producción estos cuerpos los rescata models/mail_thread_html_guard.py;
este escáner sirve para localizar y limpiar los orígenes cuando se toque
cada módulo (lo correcto es armar el cuerpo con markupsafe.Markup y escapar
los datos del usuario con markupsafe.escape).
"""
import re, sys, os, glob
CALL = re.compile(r'\.(message_post|_message_log|message_notify|_message_log_batch)\s*\(')
TAG = re.compile(r'<\s*/?\s*(p|br|b|strong|i|em|u|ul|ol|li|div|span|a|table|tr|td|th|h[1-6]|small|hr|code|pre)\b', re.I)
rows = []
for path in glob.glob('**/*.py', recursive=True):
    if '/node_modules/' in path or '/.claude/' in path or '/migrations/' in path:
        continue
    try:
        src = open(path, encoding='utf-8').read()
    except Exception:
        continue
    for m in CALL.finditer(src):
        # capturar hasta el paréntesis de cierre balanceado
        i = m.end(); depth = 1
        while i < len(src) and depth:
            c = src[i]
            if c == '(': depth += 1
            elif c == ')': depth -= 1
            i += 1
        call = src[m.start():i]
        if 'Markup' in call:
            continue
        if not TAG.search(call):
            continue
        line = src.count('\n', 0, m.start()) + 1
        module = path.split('/')[1] if '/' in path else path
        rows.append((module, path, line, m.group(1)))
by_mod = {}
for mod, path, line, fn in rows:
    by_mod.setdefault(mod, []).append((path, line, fn))
print("TOTAL llamadas con HTML en str sin Markup:", len(rows))
for mod in sorted(by_mod):
    print("\n[%s] %d" % (mod, len(by_mod[mod])))
    for path, line, fn in by_mod[mod]:
        print("   %s:%d  %s" % (path, line, fn))

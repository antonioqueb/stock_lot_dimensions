# -*- coding: utf-8 -*-
{
    'name': 'Atributos Adicionales para Lotes',
    'version': '18.0.2.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Captura dimensiones, fotografías y gestión de reservas manuales (hold) en lotes',
    'description': """
        Módulo que permite:
        - Capturar dimensiones (grosor, alto, ancho) y fotografías al recepcionar productos
        - Almacenar esta información en los lotes
        - Visualizar atributos en reportes de inventario
        - Mostrar estados de reserva y detalles de placas
        - Gestionar reservas manuales (holds) independientes de órdenes de venta
        - Expiración automática de reservas a los 10 días
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://alphaqueb.com',
    'depends': ['stock', 'sale', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_lot_hold_cron.xml',
        'views/stock_lot_views.xml',
        'views/stock_move_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_lot_image_wizard_views.xml',
        'views/stock_lot_hold_views.xml',
        'views/stock_lot_hold_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_lot_dimensions/static/src/js/image_gallery_widget.js',
            'stock_lot_dimensions/static/src/js/image_preview_widget.js',
            'stock_lot_dimensions/static/src/js/status_icons_widget.js',
            'stock_lot_dimensions/static/src/css/image_gallery.css',
            'stock_lot_dimensions/static/src/xml/image_gallery.xml',
            'stock_lot_dimensions/static/src/xml/image_preview_widget.xml',
            'stock_lot_dimensions/static/src/xml/status_icons_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
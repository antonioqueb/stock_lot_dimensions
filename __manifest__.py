# -*- coding: utf-8 -*-
{
    'name': 'Atributos Adicionales para Lotes',
    'version': '19.0.3.3.0',
    'category': 'Inventory/Inventory',
    'summary': 'Captura dimensiones, fotografías y gestión de reservas manuales (hold) en lotes',
    'description': """
        Módulo que permite:
        - Capturar dimensiones (grosor, alto, ancho) y fotografías al recepcionar productos
        - Almacenar esta información en los lotes
        - Visualizar atributos en reportes de inventario
        - Mostrar estados de reserva y detalles de placas
        - Gestionar reservas manuales (holds) independientes de órdenes de venta
        - Expiración automática de reservas a los 5 días hábiles (lunes a viernes)
        - Selección visual de placas en órdenes de reserva (estilo stone grid)
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://alphaqueb.com',
    'depends': [
        'stock',
        'sale',
        'web',
        'project',
        'mail',
        'sale_stock',
        # La clase duplicada de packing.list.import.wizard (models/stock_picking.py)
        # tiene un Many2one a documents.document: sin declarar 'documents', en una
        # instalación desde cero el grafo carga este módulo antes que Documents y
        # el registro muere con "unknown comodel_name 'documents.document'".
        'documents',
    ],
    'data': [
        'security/stock_lot_hold_security.xml',
        'security/res_company_bank_info_security.xml',
        'security/ir.model.access.csv',

        'data/stock_lot_hold_cron.xml',
        'data/res_company_bank_info_defaults.xml',
        'data/stock_lot_hold_order_sequence.xml',
        'data/migrate_hold_lines.xml',

        'reports/som_report_design.xml',
        'reports/company_bank_details_templates.xml',
        'reports/stock_lot_hold_order_sections.xml',
        'reports/stock_lot_hold_order_summary_report.xml',
        'reports/stock_lot_hold_order_detail_report.xml',
        'reports/stock_lot_hold_order_summary_report_no_prices.xml',
        'reports/stock_lot_hold_order_detail_report_no_prices.xml',
        'reports/report_sale_order_overwrite.xml',
        'reports/report_delivery_custom_detail.xml',
        'reports/pick_ticket_report.xml',
        'reports/report_sale_order_no_price.xml',
        'reports/sale_order_custom_detail_report.xml',
        'reports/report_lastpage_footer.xml',

        'views/res_company_bank_info_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_lot_group_views.xml',
        'views/stock_move_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_lot_image_wizard_views.xml',
        'views/stock_lot_hold_views.xml',
        'views/stock_lot_hold_order_views.xml',
        'views/stock_lot_hold_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/project_project_views.xml',
        'views/product_template_views.xml',
        'views/stock_lot_image_delete_wizard_views.xml',
        'views/res_company_views.xml',
        'views/stock_picking_received_by_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # JS widgets
            'stock_lot_dimensions/static/src/js/image_gallery_widget.js',
            'stock_lot_dimensions/static/src/js/image_preview_widget.js',
            'stock_lot_dimensions/static/src/js/status_icons_widget.js',
            'stock_lot_dimensions/static/src/js/hold_stone_button.js',

            # Hold stone styles
            # IMPORTANTE:
            # El archivo está en static/src/css/, no en static/src/scss/.
            # Si esta línea no está cargada, el hold funciona pero se ve sin estilo.
            'stock_lot_dimensions/static/src/css/hold_stone_styles.scss',

            # CSS base
            'stock_lot_dimensions/static/src/css/image_gallery.css',
            'stock_lot_dimensions/static/src/css/image_gallery_view.css',

            # OWL / QWeb templates
            'stock_lot_dimensions/static/src/xml/image_gallery.xml',
            'stock_lot_dimensions/static/src/xml/image_preview_widget.xml',
            'stock_lot_dimensions/static/src/xml/status_icons_widget.xml',
            'stock_lot_dimensions/static/src/xml/hold_stone_button.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
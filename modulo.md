## ./__init__.py
```py
# -*- coding: utf-8 -*-
from . import models
from . import wizard
```

## ./__manifest__.py
```py
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
        - Expiración automática de reservas a los 5 días hábiles (lunes a viernes)
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://alphaqueb.com',
    'depends': ['stock', 'sale', 'web', 'project'],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_lot_hold_cron.xml',
        'views/stock_lot_views.xml',
        'views/stock_lot_group_views.xml',
        'views/stock_move_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_lot_image_wizard_views.xml',
        'views/stock_lot_hold_views.xml',
        'views/stock_lot_hold_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/project_project_views.xml',
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
}```

## ./data/stock_lot_hold_cron.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Cron Job para expirar reservas automáticamente -->
    <record id="ir_cron_expire_lot_holds" model="ir.cron">
        <field name="name">Expirar Reservas de Lotes</field>
        <field name="model_id" ref="model_stock_lot_hold"/>
        <field name="state">code</field>
        <field name="code">model._cron_expire_holds()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">hours</field>
        <field name="active">True</field>
        <field name="priority">10</field>
    </record>
</odoo>```

## ./models/__init__.py
```py
# -*- coding: utf-8 -*-
from . import stock_lot
from . import stock_lot_image
from . import stock_move_line
from . import stock_picking
from . import stock_lot_hold 
from . import stock_quant
from . import sale_order
from . import stock_lot_group
from . import project_project
from . import res_partner```

## ./models/project_project.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectProject(models.Model):
    _inherit = 'project.project'
    
    x_es_proyecto_marmol = fields.Boolean(
        string='Es Proyecto de Mármol',
        default=False,
        help='Indica si este proyecto está relacionado con reservas de lotes de mármol'
    )```

## ./models/res_partner.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    x_es_arquitecto = fields.Boolean(
        string='Es Arquitecto',
        default=False,
        help='Indica si este contacto es un arquitecto'
    )```

## ./models/sale_order.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    # ✅ SIN VALIDACIONES
    # Puedes crear y confirmar órdenes de venta libremente
    # sin importar si hay lotes reservados o no
    pass

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """
        Override del método action_confirm para:
        1. Pasar el cliente al contexto ANTES de confirmar (para filtrar FIFO/LIFO)
        2. Limpiar lotes automáticos DESPUÉS de confirmar
        """
        _logger.info("="*80)
        _logger.info("🔵 [SALE ORDER] Iniciando action_confirm() para orden: %s", self.name)
        
        for order in self:
            if order.partner_id:
                _logger.info("🔵 [SALE ORDER] Cliente: %s (ID: %s)", 
                            order.partner_id.name, order.partner_id.id)
                
                # 🔑 CRÍTICO: Pasar el cliente al contexto ANTES de confirmar
                # Esto permite que _gather() filtre correctamente los quants con holds
                context_with_partner = dict(self.env.context)
                context_with_partner['allowed_partner_id'] = order.partner_id.id
                
                _logger.info("🔵 [SALE ORDER] ✅ Contexto actualizado con allowed_partner_id: %s", 
                            order.partner_id.id)
                
                # Ejecutar el proceso normal de confirmación CON el contexto actualizado
                res = super(SaleOrder, order.with_context(context_with_partner)).action_confirm()
            else:
                _logger.warning("🔵 [SALE ORDER] ⚠️ Orden sin cliente - confirmando sin filtro")
                res = super(SaleOrder, order).action_confirm()
        
        _logger.info("🔵 [SALE ORDER] Super action_confirm() completado")
        
        # Después de confirmar, limpiar TODOS los lotes asignados automáticamente
        for order in self:
            _logger.info("🔵 [SALE ORDER] Procesando orden: %s", order.name)
            
            # Buscar todos los pickings relacionados con esta orden
            pickings = order.picking_ids
            _logger.info("🔵 [SALE ORDER] Pickings encontrados: %s (%s)", len(pickings), pickings.mapped('name'))
            
            for picking in pickings:
                _logger.info("🔵 [SALE ORDER] Procesando picking: %s (ID: %s)", picking.name, picking.id)
                
                # SOLUCIÓN: ELIMINAR move_lines
                move_lines_to_delete = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id),
                    ('state', 'not in', ['done', 'cancel'])
                ])
                
                _logger.info("🔵 [SALE ORDER] Move lines encontradas para ELIMINAR: %s", len(move_lines_to_delete))
                
                if move_lines_to_delete:
                    for ml in move_lines_to_delete:
                        _logger.info("🔵 [SALE ORDER]   - Move Line ID: %s, Lote: %s, Producto: %s, Cantidad: %s", 
                                    ml.id, 
                                    ml.lot_id.name if ml.lot_id else 'Sin Lote',
                                    ml.product_id.name, 
                                    ml.quantity)
                    
                    try:
                        _logger.info("🔵 [SALE ORDER] ¡ELIMINANDO %s move lines!", len(move_lines_to_delete))
                        move_lines_to_delete.unlink()
                        _logger.info("🔵 [SALE ORDER] ✅ Move lines ELIMINADAS exitosamente")
                    except Exception as e:
                        _logger.error("🔵 [SALE ORDER] ❌ Error eliminando move_lines: %s", str(e))
                        _logger.exception("🔵 [SALE ORDER] Traceback:")
                else:
                    _logger.info("🔵 [SALE ORDER] No hay move_lines para eliminar")
                
                # Resetear el estado del picking si es necesario
                if picking.state == 'assigned':
                    _logger.info("🔵 [SALE ORDER] Picking está 'assigned' - cambiando a 'confirmed'")
                    try:
                        picking.write({'state': 'confirmed'})
                        _logger.info("🔵 [SALE ORDER] ✅ Picking state actualizado")
                    except Exception as e:
                        _logger.error("🔵 [SALE ORDER] ⚠️ No se pudo cambiar state del picking: %s", str(e))
                
                # Resetear los moves también
                for move in picking.move_ids:
                    if move.state == 'assigned':
                        _logger.info("🔵 [SALE ORDER] Move %s está 'assigned' - reseteando", move.id)
                        try:
                            move.write({'state': 'confirmed'})
                            _logger.info("🔵 [SALE ORDER] ✅ Move %s reseteado", move.id)
                        except Exception as e:
                            _logger.error("🔵 [SALE ORDER] ⚠️ Error reseteando move: %s", str(e))
                
                # INVALIDAR CACHE para forzar recarga
                self.env['stock.move.line'].invalidate_model()
                self.env['stock.move'].invalidate_model()
                self.env['stock.picking'].invalidate_model()
                _logger.info("🔵 [SALE ORDER] ✅ Cache invalidado")
                
                # Verificación final
                move_lines_verificacion = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id)
                ])
                
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
                _logger.info("🔵 [SALE ORDER] VERIFICACIÓN FINAL")
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
                _logger.info("🔵 [SALE ORDER] Total move_lines después: %s", len(move_lines_verificacion))
                
                if move_lines_verificacion:
                    _logger.warning("🔵 [SALE ORDER] ⚠️ AÚN HAY MOVE LINES:")
                    for ml in move_lines_verificacion:
                        _logger.info("🔵 [SALE ORDER]   - Move Line ID: %s, Lote: %s, Estado: %s", 
                                    ml.id, 
                                    ml.lot_id.name if ml.lot_id else '✅ VACÍO',
                                    ml.state)
                else:
                    _logger.info("🔵 [SALE ORDER] ✅✅✅ PERFECTO - NO HAY MOVE LINES")
                    _logger.info("🔵 [SALE ORDER] ✅✅✅ Picking completamente limpio")
                
                _logger.info("🔵 [SALE ORDER] ═══════════════════════════════════════════")
        
        _logger.info("🔵 [SALE ORDER] action_confirm() finalizado")
        _logger.info("="*80)
        return res```

## ./models/stock_lot.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLot(models.Model):
    _inherit = 'stock.lot'

    x_grosor = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros'
    )
    
    x_alto = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros'
    )
    
    x_ancho = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros'
    )

    x_tipo = fields.Selection([
        ('placa', 'Placa'),
        ('formato', 'Formato'),
    ], string='Tipo', help='Tipo de producto: Placa o Formato')
    
    
    x_bloque = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen'
    )

    x_atado = fields.Char(
        string='Atado',
        help='Identificación del atado'
    )

    x_grupo = fields.Many2many(
        'stock.lot.group',
        string='Grupo',
        help='Etiquetas de grupo para clasificación'
    )

    x_pedimento = fields.Char(
        string='Pedimento',
        help='Número de pedimento aduanal'
    )

    x_contenedor = fields.Char(
        string='Contenedor',
        help='Número de contenedor'
    )

    x_referencia_proveedor = fields.Char(
        string='Referencia Proveedor',
        help='Referencia del proveedor'
    )
    
    x_fotografia_ids = fields.One2many(
        'stock.lot.image',
        'lot_id',
        string='Fotografías',
        help='Fotografías del producto/lote'
    )
    
    x_fotografia_principal = fields.Binary(
        string='Foto Principal',
        compute='_compute_fotografia_principal',
        store=False
    )
    
    x_tiene_fotografias = fields.Boolean(
        string='Tiene Fotos',
        compute='_compute_tiene_fotografias',
        store=True
    )
    
    x_cantidad_fotos = fields.Integer(
        string='# Fotos',
        compute='_compute_cantidad_fotos',
        store=True
    )
    
    x_detalles_placa = fields.Text(
        string='Detalles de la Placa',
        help='Detalles especiales: rota, barreno, release, etc.'
    )

    @api.depends('x_fotografia_ids')
    def _compute_fotografia_principal(self):
        """Obtener la primera fotografía como principal"""
        for record in self:
            if record.x_fotografia_ids:
                record.x_fotografia_principal = record.x_fotografia_ids[0].image
            else:
                record.x_fotografia_principal = False

    @api.depends('x_fotografia_ids')
    def _compute_tiene_fotografias(self):
        """Verificar si el lote tiene fotografías"""
        for record in self:
            record.x_tiene_fotografias = bool(record.x_fotografia_ids)

    @api.depends('x_fotografia_ids')
    def _compute_cantidad_fotos(self):
        """Contar número de fotografías"""
        for record in self:
            record.x_cantidad_fotos = len(record.x_fotografia_ids)

    def action_view_images(self):
        """Abrir vista de galería de imágenes del lote"""
        self.ensure_one()
        return {
            'name': f'Fotografías de {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,tree,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {
                'default_lot_id': self.id,
                'create': True,
            },
            'target': 'current',
        }```

## ./models/stock_lot_group.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields

class StockLotGroup(models.Model):
    _name = 'stock.lot.group'
    _description = 'Grupos/Etiquetas de Lotes'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre del grupo/etiqueta'
    )
    
    color = fields.Integer(
        string='Color',
        help='Color de la etiqueta en la interfaz'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )```

## ./models/stock_lot_hold.py
```py
# ./models/stock_lot_hold.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class StockLotHold(models.Model):
    _name = 'stock.lot.hold'
    _description = 'Reservas Manuales de Lotes'
    _order = 'fecha_inicio desc'
    
    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    
    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True,
        index=True
    )
    
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        related='lot_id.product_id',
        store=True,
        readonly=True
    )
    
    ubicacion_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        related='quant_id.location_id',
        store=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        readonly=True,
        index=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        readonly=True,
        index=True
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        readonly=True
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        readonly=True
    )
    
    fecha_inicio = fields.Datetime(
        string='Fecha Inicio',
        default=fields.Datetime.now,
        required=True,
        readonly=True
    )
    
    fecha_expiracion = fields.Datetime(
        string='Fecha Expiración',
        required=True,
        readonly=True
    )
    
    estado = fields.Selection([
        ('activo', 'Activo'),
        ('expirado', 'Expirado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='activo', required=True, index=True)
    
    notas = fields.Text(string='Notas')
    
    dias_restantes = fields.Integer(
        string='Días Hábiles Restantes',
        compute='_compute_dias_restantes'
    )

    @api.depends('lot_id', 'partner_id')
    def _compute_name(self):
        for record in self:
            if record.lot_id and record.partner_id:
                record.name = f"{record.lot_id.name} - {record.partner_id.name}"
            else:
                record.name = "Hold"

    @api.depends('fecha_expiracion', 'estado')
    def _compute_dias_restantes(self):
        ahora = fields.Datetime.now()
        for record in self:
            if record.estado != 'activo':
                record.dias_restantes = 0
            elif record.fecha_expiracion <= ahora:
                record.dias_restantes = 0
            else:
                record.dias_restantes = record._calcular_dias_habiles_entre(ahora, record.fecha_expiracion)

    def _calcular_dias_habiles_entre(self, fecha_inicio, fecha_fin):
        dias = 0
        fecha_actual = fecha_inicio
        while fecha_actual.date() < fecha_fin.date():
            if fecha_actual.weekday() < 5:
                dias += 1
            fecha_actual += timedelta(days=1)
        return dias

    def _calcular_dias_habiles(self, fecha_inicio, dias_habiles):
        fecha_actual = fecha_inicio
        dias_agregados = 0
        while dias_agregados < dias_habiles:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:
                dias_agregados += 1
        return fecha_actual

    @api.model
    def create(self, vals):
        if 'fecha_expiracion' not in vals and vals.get('fecha_inicio'):
            fecha_inicio = fields.Datetime.to_datetime(vals['fecha_inicio'])
            vals['fecha_expiracion'] = self._calcular_dias_habiles(fecha_inicio, 5)
        return super().create(vals)

    def action_renovar_hold(self):
        self.ensure_one()
        if self.estado != 'activo':
            raise UserError('Solo se pueden renovar reservas activas.')
        
        nueva_expiracion = self._calcular_dias_habiles(fields.Datetime.now(), 5)
        self.write({'fecha_expiracion': nueva_expiracion})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Renovado!',
                'message': f'Reserva extendida hasta {nueva_expiracion.strftime("%d/%m/%Y %H:%M")}',
                'type': 'success',
            }
        }

    def action_cancelar_hold(self):
        self.ensure_one()
        if self.estado != 'activo':
            raise UserError('Esta reserva ya no está activa.')
        
        self.write({'estado': 'cancelado'})

    @api.model
    def _cron_expire_holds(self):
        ahora = fields.Datetime.now()
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', ahora)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            _logger.info(f"Se expiraron {len(holds_expirados)} reservas de lotes")```

## ./models/stock_lot_image.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLotImage(models.Model):
    _name = 'stock.lot.image'
    _description = 'Fotografías de Lotes'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True,
        default='Fotografía'
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización de las fotografías'
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    image = fields.Binary(
        string='Imagen',
        required=True,
        attachment=True
    )
    
    image_small = fields.Binary(
        string='Miniatura',
        compute='_compute_image_small',
        store=True
    )
    
    fecha_captura = fields.Datetime(
        string='Fecha de Captura',
        default=fields.Datetime.now,
        readonly=True
    )
    
    notas = fields.Text(
        string='Notas'
    )

    @api.depends('image')
    def _compute_image_small(self):
        """Generar miniatura de la imagen"""
        for record in self:
            if record.image:
                # Odoo maneja automáticamente el redimensionamiento
                record.image_small = record.image
            else:
                record.image_small = False
```

## ./models/stock_move_line.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # Campos temporales para captura en recepción
    x_grosor_temp = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros (se guardará en el lote)'
    )
    
    x_alto_temp = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros (se guardará en el lote)'
    )
    
    x_ancho_temp = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros (se guardará en el lote)'
    )

    x_tipo_temp = fields.Selection([
        ('placa', 'Placa'),
        ('formato', 'Formato'),
    ], string='Tipo', help='Tipo de producto (se guardará en el lote)')
    
    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)'
    )

    x_atado_temp = fields.Char(
        string='Atado',
        help='Identificación del atado (se guardará en el lote)'
    )
    
   
    
    x_grupo_temp = fields.Many2many(
        'stock.lot.group',
        string='Grupo',
        help='Grupos del lote (se guardarán en el lote)'
    )

    x_pedimento_temp = fields.Char(
        string='Pedimento',
        help='Número de pedimento (se guardará en el lote)'
    )

    x_contenedor_temp = fields.Char(
        string='Contenedor',
        help='Número de contenedor (se guardará en el lote)'
    )

    x_referencia_proveedor_temp = fields.Char(
        string='Referencia Proveedor',
        help='Referencia del proveedor (se guardará en el lote)'
    )
    
    # Campo computed para saber si es recepción
    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False
    )
    
    # Campos related para mostrar en historial de movimientos
    x_grosor_lote = fields.Float(
        related='lot_id.x_grosor',
        string='Grosor Lote (cm)',
        readonly=True,
        store=False
    )
    
    x_alto_lote = fields.Float(
        related='lot_id.x_alto',
        string='Alto Lote (m)',
        readonly=True,
        store=False
    )
    
    x_ancho_lote = fields.Float(
        related='lot_id.x_ancho',
        string='Ancho Lote (m)',
        readonly=True,
        store=False
    )

    x_tipo_lote = fields.Selection(
        related='lot_id.x_tipo',
        string='Tipo Lote',
        readonly=True,
        store=False
    )

    
    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False
    )

    x_atado_lote = fields.Char(
        related='lot_id.x_atado',
        string='Atado Lote',
        readonly=True,
        store=False
    )
    

    x_grupo_lote = fields.Many2many(
        related='lot_id.x_grupo',
        string='Grupo Lote',
        readonly=True,
        store=False
    )

    x_pedimento_lote = fields.Char(
        related='lot_id.x_pedimento',
        string='Pedimento Lote',
        readonly=True,
        store=False
    )

    x_contenedor_lote = fields.Char(
        related='lot_id.x_contenedor',
        string='Contenedor Lote',
        readonly=True,
        store=False
    )

    x_referencia_proveedor_lote = fields.Char(
        related='lot_id.x_referencia_proveedor',
        string='Ref. Proveedor Lote',
        readonly=True,
        store=False
    )
    
    x_fotografia_principal_lote = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto Lote',
        readonly=True,
        store=False
    )
    
    x_cantidad_fotos_lote = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos Lote',
        readonly=True,
        store=False
    )

    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción"""
        for line in self:
            line.x_is_incoming = line.picking_id and line.picking_id.picking_type_code == 'incoming'

    def _get_lotes_disponibles_ids(self):
        """
        🔍 FILTRADO DE LOTES - CON DEPURACIÓN COMPLETA
        """
        self.ensure_one()
        
        _logger.info("🔵"*50)
        _logger.info("🔵 [FILTRO LOTES] _get_lotes_disponibles_ids() INICIANDO")
        _logger.info("🔵 [FILTRO LOTES] Move Line ID: %s", self.id)
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if not self.picking_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY PICKING - Retornando lista vacía")
            return []
            
        if self.picking_id.picking_type_code != 'outgoing':
            _logger.info("🔵 [FILTRO LOTES] ⏭️ Picking NO es outgoing (es: %s) - No filtrar", 
                        self.picking_id.picking_type_code)
            return []
        
        _logger.info("🔵 [FILTRO LOTES] ✅ Picking es OUTGOING: %s", self.picking_id.name)
        
        # Obtener el cliente del picking
        cliente_picking = self.picking_id.partner_id
        _logger.info("🔵 [FILTRO LOTES] Cliente del picking: %s (ID: %s)", 
                    cliente_picking.name if cliente_picking else 'SIN CLIENTE',
                    cliente_picking.id if cliente_picking else 'N/A')
        
        if self.move_id and self.move_id.sale_line_id:
            cliente_picking = self.move_id.sale_line_id.order_id.partner_id
            _logger.info("🔵 [FILTRO LOTES] ✅ Cliente actualizado desde sale_line_id: %s (ID: %s)", 
                        cliente_picking.name, cliente_picking.id)
        
        if not cliente_picking:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY CLIENTE - Retornando lista vacía")
            return []
            
        if not self.product_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY PRODUCTO - Retornando lista vacía")
            return []
            
        if not self.location_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY UBICACIÓN - Retornando lista vacía")
            return []
        
        _logger.info("🔵 [FILTRO LOTES] Producto: %s (ID: %s)", self.product_id.name, self.product_id.id)
        _logger.info("🔵 [FILTRO LOTES] Ubicación: %s (ID: %s)", self.location_id.name, self.location_id.id)
        
        # Buscar todos los quants del producto en la ubicación
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('quantity', '>', 0),
        ])
        
        _logger.info("🔵 [FILTRO LOTES] Total quants encontrados: %s", len(quants))
        
        # Filtrar lotes válidos
        lotes_validos = []
        
        for quant in quants:
            if quant.lot_id:
                lote_nombre = quant.lot_id.name
                lote_id = quant.lot_id.id
                tiene_hold = quant.x_tiene_hold
                
                _logger.info("🔵 [FILTRO LOTES] ─────────────────────────────────────")
                _logger.info("🔵 [FILTRO LOTES] Analizando Lote: %s (ID: %s)", lote_nombre, lote_id)
                _logger.info("🔵 [FILTRO LOTES] Cantidad: %.2f", quant.quantity)
                _logger.info("🔵 [FILTRO LOTES] Tiene Hold: %s", tiene_hold)
                
                # CASO 1: Sin hold → Disponible para TODOS
                if not tiene_hold:
                    _logger.info("🔵 [FILTRO LOTES] ✅ SIN HOLD - Agregando a lista válida")
                    lotes_validos.append(lote_id)
                    continue
                
                # CASO 2: Con hold → Verificar para quién es
                if quant.x_hold_activo_id:
                    hold_partner = quant.x_hold_activo_id.partner_id
                    hold_partner_id = hold_partner.id if hold_partner else None
                    hold_partner_name = hold_partner.name if hold_partner else 'SIN CLIENTE'
                    
                    _logger.info("🔵 [FILTRO LOTES] Hold encontrado:")
                    _logger.info("🔵 [FILTRO LOTES]   - Partner Hold: %s (ID: %s)", 
                                hold_partner_name, hold_partner_id)
                    _logger.info("🔵 [FILTRO LOTES]   - Partner Picking: %s (ID: %s)", 
                                cliente_picking.name, cliente_picking.id)
                    
                    if hold_partner_id == cliente_picking.id:
                        _logger.info("🔵 [FILTRO LOTES] ✅ HOLD PARA ESTE CLIENTE - Agregando a lista válida")
                        lotes_validos.append(lote_id)
                    else:
                        _logger.warning("🔵 [FILTRO LOTES] ❌ HOLD PARA OTRO CLIENTE - NO agregando")
                        _logger.warning("🔵 [FILTRO LOTES]    Este lote NO debe aparecer en la lista")
                else:
                    _logger.warning("🔵 [FILTRO LOTES] ⚠️ Tiene hold pero sin x_hold_activo_id - NO agregando")
        
        _logger.info("🔵 [FILTRO LOTES] ═════════════════════════════════════════")
        _logger.info("🔵 [FILTRO LOTES] RESUMEN FINAL:")
        _logger.info("🔵 [FILTRO LOTES] Total quants analizados: %s", len(quants))
        _logger.info("🔵 [FILTRO LOTES] Lotes válidos encontrados: %s", len(lotes_validos))
        _logger.info("🔵 [FILTRO LOTES] IDs de lotes válidos: %s", lotes_validos)
        _logger.info("🔵 [FILTRO LOTES] _get_lotes_disponibles_ids() FINALIZADO")
        _logger.info("🔵"*50)
        
        return lotes_validos

    @api.constrains('lot_id', 'picking_id', 'state')
    def _check_lot_hold(self):
        """
        🔒 CONSTRAINT: Validación de holds al asignar/confirmar lotes
        
        IMPORTANTE:
        - Respeta el contexto skip_hold_validation cuando los lotes ya fueron validados
        - Solo valida en pickings de salida (outgoing)
        - Solo valida cuando el lote ya está asignado
        - Solo valida si hay un hold activo (x_tiene_hold=True)
        - Permite holds del mismo cliente
        - Bloquea holds de otros clientes
        """
        # 🔑 BYPASS: Si el contexto indica que ya se validó, saltar
        if self._context.get('skip_hold_validation'):
            _logger.info("🔒 [CONSTRAINT] BYPASS activado - Saltando validación de holds")
            return
        
        for line in self:
            _logger.info("🔒" * 50)
            _logger.info("🔒 [CONSTRAINT] _check_lot_hold() EJECUTADO")
            _logger.info("🔒 [CONSTRAINT] Move Line ID: %s", line.id)
            _logger.info("🔒 [CONSTRAINT] Lote: %s (ID: %s)", 
                        line.lot_id.name if line.lot_id else 'Sin lote', 
                        line.lot_id.id if line.lot_id else None)
            _logger.info("🔒 [CONSTRAINT] Location: %s (ID: %s)", 
                        line.location_id.name if line.location_id else 'Sin location', 
                        line.location_id.id if line.location_id else None)
            _logger.info("🔒 [CONSTRAINT] Picking: %s", 
                        line.picking_id.name if line.picking_id else 'Sin picking')
            
            # Skip si no hay lote asignado
            if not line.lot_id:
                _logger.info("🔒 [CONSTRAINT] ⏭️ Sin lote - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Skip si no es picking de salida
            if not line.picking_id or line.picking_id.picking_type_code != 'outgoing':
                _logger.info("🔒 [CONSTRAINT] ⏭️ No es picking outgoing - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Obtener cliente del picking
            partner = line.picking_id.partner_id
            _logger.info("🔒 [CONSTRAINT] Cliente: %s (ID: %s)", 
                        partner.name if partner else 'Sin cliente',
                        partner.id if partner else None)
            
            if not partner:
                _logger.info("🔒 [CONSTRAINT] ⏭️ Sin cliente - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Buscar quant específico CON HOLD ACTIVO para este lote Y ubicación
            quant = self.env['stock.quant'].search([
                ('lot_id', '=', line.lot_id.id),
                ('location_id', '=', line.location_id.id),
                ('quantity', '>', 0),
                ('x_tiene_hold', '=', True),  # 🔑 FILTRO CRÍTICO: Solo quants con hold activo
            ], limit=1)
            
            if not quant:
                _logger.info("🔒 [CONSTRAINT] ✅ No se encontró quant con hold activo - OK para usar")
                _logger.info("🔒" * 50)
                continue
            
            _logger.info("🔒 [CONSTRAINT] ⚠️ Quant con hold encontrado - ID: %s", quant.id)
            
            hold_partner = quant.x_hold_activo_id.partner_id
            _logger.info("🔒 [CONSTRAINT] Hold para: %s (ID: %s)", 
                        hold_partner.name if hold_partner else 'Sin partner',
                        hold_partner.id if hold_partner else None)
            
            if hold_partner and hold_partner.id != partner.id:
                dias_restantes = quant.x_hold_dias_restantes
                fecha_expiracion = quant.x_hold_expira.strftime('%d/%m/%Y %H:%M') if quant.x_hold_expira else 'N/A'
                
                _logger.error("🔒 [CONSTRAINT] ❌❌❌ BLOQUEANDO - Hold para otro cliente")
                _logger.info("🔒" * 50)
                
                raise ValidationError(
                    f"🔒 NO PUEDE USAR ESTE LOTE\n\n"
                    f"El lote '{line.lot_id.name}' está RESERVADO para:\n"
                    f"👤 {hold_partner.name}\n"
                    f"📅 Hasta: {fecha_expiracion}\n"
                    f"⏱️ Días restantes: {dias_restantes}\n\n"
                    f"❌ Esta entrega es para '{partner.name}'\n\n"
                    f"Por favor, seleccione un lote disponible.\n"
                    f"Los lotes apartados para otros clientes no aparecen en la lista."
                )
            else:
                _logger.info("🔒 [CONSTRAINT] ✅ Hold es para este cliente - OK")
            
            _logger.info("🔒" * 50)

    @api.onchange('product_id', 'location_id', 'picking_id')
    def _onchange_product_location_filter_lots(self):
        """
        🎨 ONCHANGE - Filtrar lotes cuando el usuario cambia producto/ubicación
        """
        _logger.info("🟢"*50)
        _logger.info("🟢 [ONCHANGE] _onchange_product_location_filter_lots() EJECUTADO")
        
        if not self.product_id or not self.picking_id:
            _logger.info("🟢 [ONCHANGE] Sin producto o picking - retornando {}")
            return {}
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if self.picking_id.picking_type_code != 'outgoing':
            _logger.info("🟢 [ONCHANGE] Picking NO es outgoing - retornando {}")
            return {}
        
        _logger.info("🟢 [ONCHANGE] Llamando a _get_lotes_disponibles_ids()...")
        lotes_validos = self._get_lotes_disponibles_ids()
        
        # Retornar dominio que filtra los lotes
        if lotes_validos:
            domain_result = {
                'domain': {
                    'lot_id': [
                        ('id', 'in', lotes_validos),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
            _logger.info("🟢 [ONCHANGE] ✅ Retornando dominio con %s lotes", len(lotes_validos))
            _logger.info("🟢 [ONCHANGE] Dominio: %s", domain_result)
            _logger.info("🟢"*50)
            return domain_result
        else:
            domain_result = {
                'domain': {
                    'lot_id': [('id', '=', False)]
                }
            }
            _logger.info("🟢 [ONCHANGE] ⚠️ NO HAY LOTES VÁLIDOS - Retornando dominio vacío")
            _logger.info("🟢"*50)
            return domain_result

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """
        Cargar dimensiones del lote si ya existen y calcular cantidad.
        """
        if self.lot_id:
            # Cargar valores en campos temporales
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
            self.x_bloque_temp = self.lot_id.x_bloque
            self.x_atado_temp = self.lot_id.x_atado
            self.x_tipo_temp = self.lot_id.x_tipo 
            
            if self.picking_id:
                if self.picking_id.picking_type_code == 'incoming':
                    # RECEPCIÓN: Calcular por dimensiones
                    if self.lot_id.x_alto and self.lot_id.x_ancho:
                        self.qty_done = self.lot_id.x_alto * self.lot_id.x_ancho
                
                elif self.picking_id.picking_type_code == 'outgoing':
                    # ENTREGA: Buscar cantidad disponible del lote
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', self.lot_id.id),
                        ('location_id', '=', self.location_id.id),
                        ('product_id', '=', self.product_id.id)
                    ], limit=1)
                    
                    if quant:
                        cantidad_disponible = quant.available_quantity
                        if cantidad_disponible > 0:
                            if self.move_id and self.move_id.product_uom_qty:
                                self.qty_done = min(cantidad_disponible, self.move_id.product_uom_qty)
                            else:
                                self.qty_done = cantidad_disponible
                        else:
                            self.qty_done = 0.0
                    else:
                        self.qty_done = 0.0

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular automáticamente qty_done (m²) cuando se ingresan alto y ancho"""
        if self.picking_id and self.picking_id.picking_type_code == 'incoming':
            if self.x_alto_temp and self.x_ancho_temp:
                self.qty_done = self.x_alto_temp * self.x_ancho_temp

    def write(self, vals):
        """Guardar dimensiones en el lote al confirmar (solo en recepciones)"""
        _logger.info("🟣"*50)
        _logger.info("🟣 [WRITE] write() EJECUTADO en stock.move.line")
        _logger.info("🟣 [WRITE] vals: %s", vals)
        
        # ================================================================
        # VALIDACIÓN CRÍTICA: Si se está modificando lot_id, verificar hold
        # ================================================================
        if 'lot_id' in vals and vals['lot_id']:
            _logger.info("🟣 [WRITE] ⚠️ Detectado cambio de lot_id a: %s", vals['lot_id'])
            
            for line in self:
                # Solo validar en pickings de salida (entregas)
                if line.picking_id and line.picking_id.picking_type_code == 'outgoing':
                    _logger.info("🟣 [WRITE] Picking es OUTGOING - Validando hold")
                    _logger.info("🟣 [WRITE] Picking: %s", line.picking_id.name)
                    
                    # Obtener el cliente del picking
                    cliente_picking = line.picking_id.partner_id
                    if line.move_id and line.move_id.sale_line_id:
                        cliente_picking = line.move_id.sale_line_id.order_id.partner_id
                    
                    if cliente_picking:
                        _logger.info("🟣 [WRITE] Cliente picking: %s (ID: %s)", 
                                    cliente_picking.name, cliente_picking.id)
                        
                        # Buscar el quant del lote que se intenta asignar
                        new_lot = self.env['stock.lot'].browse(vals['lot_id'])
                        _logger.info("🟣 [WRITE] Nuevo lote a asignar: %s (ID: %s)", 
                                    new_lot.name, new_lot.id)
                        
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', vals['lot_id']),
                            ('location_id', '=', line.location_id.id),
                            ('product_id', '=', line.product_id.id)
                        ], limit=1)
                        
                        if quant:
                            _logger.info("🟣 [WRITE] Quant encontrado - ID: %s", quant.id)
                            _logger.info("🟣 [WRITE] Tiene hold: %s", quant.x_tiene_hold)
                            
                            # Si tiene hold, verificar que sea para este cliente
                            if quant.x_tiene_hold and quant.x_hold_activo_id:
                                hold_partner = quant.x_hold_activo_id.partner_id
                                _logger.info("🟣 [WRITE] Hold partner: %s (ID: %s)", 
                                            hold_partner.name, hold_partner.id)
                                
                                # Si el hold NO es para este cliente, BLOQUEAR
                                if hold_partner.id != cliente_picking.id:
                                    _logger.error("🟣 [WRITE] ❌❌❌ BLOQUEANDO WRITE!")
                                    _logger.error("🟣 [WRITE] Lote tiene hold para otro cliente")
                                    
                                    raise UserError(
                                        f"🔒 NO PUEDE ASIGNAR ESTE LOTE\n\n"
                                        f"El lote '{new_lot.name}' está RESERVADO para:\n"
                                        f"👤 {hold_partner.name}\n"
                                        f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                                        f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                                        f"❌ Esta entrega es para '{cliente_picking.name}'\n\n"
                                        f"Por favor, seleccione un lote disponible de la lista."
                                    )
                                else:
                                    _logger.info("🟣 [WRITE] ✅ Hold es para este cliente - Permitiendo")
                            else:
                                _logger.info("🟣 [WRITE] ✅ No tiene hold - Permitiendo")
                        else:
                            _logger.warning("🟣 [WRITE] ⚠️ No se encontró quant para este lote")
                    else:
                        _logger.warning("🟣 [WRITE] ⚠️ No hay cliente en el picking")
                else:
                    if line.picking_id:
                        _logger.info("🟣 [WRITE] Picking NO es outgoing (es: %s) - No validar", 
                                    line.picking_id.picking_type_code)
        
        _logger.info("🟣 [WRITE] ✅ Validaciones pasadas - Ejecutando super().write()")
        _logger.info("🟣"*50)
        
        # Primero ejecutar el write original
        result = super().write(vals)
        
        # Después del write, verificar si hay dimensiones que guardar en el lote
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp', 'x_bloque_temp', 'x_atado_temp']
        has_dimensions = any(field in vals for field in dimension_fields)
        
        # Si se modificó el lote_id o hay dimensiones, actualizar el lote
        if 'lot_id' in vals or has_dimensions:
            for line in self:
                if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    lot_vals = {}
                    
                    if line.x_grosor_temp:
                        lot_vals['x_grosor'] = line.x_grosor_temp
                    if line.x_alto_temp:
                        lot_vals['x_alto'] = line.x_alto_temp
                    if line.x_ancho_temp:
                        lot_vals['x_ancho'] = line.x_ancho_temp
                    if line.x_bloque_temp:
                        lot_vals['x_bloque'] = line.x_bloque_temp
                    if line.x_atado_temp:
                        lot_vals['x_atado'] = line.x_atado_temp
                    if line.x_tipo_temp:
                        lot_vals['x_tipo'] = line.x_tipo_temp
                    if line.x_grupo_temp:
                        lot_vals['x_grupo'] = [(6, 0, line.x_grupo_temp.ids)]
                    if line.x_pedimento_temp:
                        lot_vals['x_pedimento'] = line.x_pedimento_temp
                    if line.x_contenedor_temp:
                        lot_vals['x_contenedor'] = line.x_contenedor_temp
                    if line.x_referencia_proveedor_temp:
                        lot_vals['x_referencia_proveedor'] = line.x_referencia_proveedor_temp
                    
                    if lot_vals:
                        line.lot_id.write(lot_vals)
        
        # Calcular qty_done si se modifican alto o ancho
        if ('x_alto_temp' in vals or 'x_ancho_temp' in vals) and 'qty_done' not in vals:
            for line in self:
                if line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    alto = line.x_alto_temp
                    ancho = line.x_ancho_temp
                    if alto and ancho:
                        super(StockMoveLine, line).write({'qty_done': alto * ancho})
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear"""
        for vals in vals_list:
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    if vals.get('x_alto_temp') and vals.get('x_ancho_temp'):
                        vals['qty_done'] = vals['x_alto_temp'] * vals['x_ancho_temp']
        
        lines = super().create(vals_list)
        
        for line, vals in zip(lines, vals_list):
            if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                lot_vals = {}
                
                if line.x_grosor_temp:
                    lot_vals['x_grosor'] = line.x_grosor_temp
                if line.x_alto_temp:
                    lot_vals['x_alto'] = line.x_alto_temp
                if line.x_ancho_temp:
                    lot_vals['x_ancho'] = line.x_ancho_temp
                if line.x_bloque_temp:
                    lot_vals['x_bloque'] = line.x_bloque_temp
                if line.x_tipo_temp:
                    lot_vals['x_tipo'] = line.x_tipo_temp    
                if line.x_grupo_temp:
                    lot_vals['x_grupo'] = [(6, 0, line.x_grupo_temp.ids)]
                if line.x_pedimento_temp:
                    lot_vals['x_pedimento'] = line.x_pedimento_temp
                if line.x_contenedor_temp:
                    lot_vals['x_contenedor'] = line.x_contenedor_temp
                if line.x_referencia_proveedor_temp:
                    lot_vals['x_referencia_proveedor'] = line.x_referencia_proveedor_temp
                
                if lot_vals:
                    line.lot_id.write(lot_vals)
        
        return lines

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'Debe seleccionar un lote primero',
                    'type': 'warning',
                }
            }
        
        return {
            'name': 'Agregar Fotografía',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            }
        }
    
    def action_view_lot_photos(self):
        """Ver fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            return False
        
        return {
            'name': f'Fotografías - {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        🔒 FILTRADO ADICIONAL - En name_search
        
        Este método se ejecuta cuando Odoo busca lotes para el selector.
        Aquí agregamos el filtrado de holds TAMBIÉN en la búsqueda.
        """
        _logger.info("🟡"*50)
        _logger.info("🟡 [NAME_SEARCH] name_search() EJECUTADO en stock.lot")
        _logger.info("🟡 [NAME_SEARCH] name: %s", name)
        _logger.info("🟡 [NAME_SEARCH] args: %s", args)
        _logger.info("🟡 [NAME_SEARCH] Context: %s", self.env.context)
        
        # Verificar si estamos en el contexto de una move_line
        move_line_id = self.env.context.get('move_line_id')
        
        if move_line_id:
            _logger.info("🟡 [NAME_SEARCH] ✅ Contexto tiene move_line_id: %s", move_line_id)
            
            move_line = self.env['stock.move.line'].browse(move_line_id)
            
            if move_line.picking_id and move_line.picking_id.picking_type_code == 'outgoing':
                _logger.info("🟡 [NAME_SEARCH] ✅ Es un picking OUTGOING - Aplicando filtro")
                
                # Obtener cliente
                cliente_picking = move_line.picking_id.partner_id
                if move_line.move_id and move_line.move_id.sale_line_id:
                    cliente_picking = move_line.move_id.sale_line_id.order_id.partner_id
                
                if cliente_picking:
                    _logger.info("🟡 [NAME_SEARCH] Cliente: %s (ID: %s)", 
                                cliente_picking.name, cliente_picking.id)
                    
                    # Buscar quants válidos
                    domain = [
                        ('product_id', '=', move_line.product_id.id),
                        ('location_id', '=', move_line.location_id.id),
                        ('quantity', '>', 0),
                    ]
                    
                    quants = self.env['stock.quant'].search(domain)
                    _logger.info("🟡 [NAME_SEARCH] Quants encontrados: %s", len(quants))
                    
                    lotes_validos = []
                    for quant in quants:
                        if quant.lot_id:
                            if not quant.x_tiene_hold:
                                lotes_validos.append(quant.lot_id.id)
                            elif quant.x_hold_activo_id and quant.x_hold_activo_id.partner_id.id == cliente_picking.id:
                                lotes_validos.append(quant.lot_id.id)
                    
                    _logger.info("🟡 [NAME_SEARCH] Lotes válidos: %s", lotes_validos)
                    
                    # Agregar filtro a args
                    if args is None:
                        args = []
                    args = list(args) + [('id', 'in', lotes_validos)]
                    
                    _logger.info("🟡 [NAME_SEARCH] Args actualizado: %s", args)
        
        _logger.info("🟡"*50)
        
        # Llamar al método original con args posiblemente modificado
        return super(StockLot, self).name_search(name=name, args=args, operator=operator, limit=limit)```

## ./models/stock_picking.py
```py
# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_assign(self):
        """Override para filtrar quants con hold al reservar"""
        _logger.info("🟢 [STOCK PICKING] action_assign() llamado para picking: %s", self.mapped('name'))
        
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.partner_id:
                # ✅ CORRECCIÓN: Pasar el cliente permitido Y la empresa en el contexto
                company_id = picking.company_id.id if picking.company_id else self.env.company.id
                self = self.with_context(
                    allowed_partner_id=picking.partner_id.id,
                    company_id=company_id
                )
        
        result = super(StockPicking, self).action_assign()
        _logger.info("🟢 [STOCK PICKING] action_assign() completado")
        return result
    
    def _action_assign(self):
        """
        Override para limpiar lotes automáticos después de la asignación
        """
        _logger.info("="*80)
        _logger.info("🟡 [STOCK PICKING] _action_assign() INICIANDO para picking(s): %s", self.mapped('name'))
        
        # Ejecutar el proceso normal de asignación
        res = super(StockPicking, self)._action_assign()
        _logger.info("🟡 [STOCK PICKING] Super _action_assign() completado")
        
        # Después de la asignación, limpiar TODOS los lotes que se asignaron automáticamente
        for picking in self:
            _logger.info("🟡 [STOCK PICKING] Procesando picking: %s (ID: %s)", picking.name, picking.id)
            _logger.info("🟡 [STOCK PICKING] Sale Order: %s", picking.sale_id.name if picking.sale_id else 'No tiene sale_id')
            _logger.info("🟡 [STOCK PICKING] Picking Type: %s", picking.picking_type_code)
            _logger.info("🟡 [STOCK PICKING] Company: %s (ID: %s)", 
                        picking.company_id.name if picking.company_id else 'N/A',
                        picking.company_id.id if picking.company_id else 'N/A')
            
            # Verificar si este picking viene de una orden de venta
            if picking.sale_id:
                _logger.info("🟡 [STOCK PICKING] ✅ Picking viene de Sale Order - procediendo a limpiar lotes")
                
                # Buscar todas las stock.move.line de este picking
                move_lines = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id)
                ])
                
                _logger.info("🟡 [STOCK PICKING] Move lines encontradas: %s", len(move_lines))
                
                for ml in move_lines:
                    _logger.info("🟡 [STOCK PICKING]   - Move Line ID: %s, Lote: %s, Producto: %s, Cantidad: %s, Estado: %s", 
                                ml.id, 
                                ml.lot_id.name if ml.lot_id else 'Sin Lote',
                                ml.product_id.name, 
                                ml.quantity,
                                ml.state)
                
                # Limpiar los lotes de todas las líneas
                if move_lines:
                    _logger.info("🟡 [STOCK PICKING] ¡LIMPIANDO LOTES AHORA! Actualizando %s líneas...", len(move_lines))
                    
                    try:
                        move_lines.write({
                            'lot_id': False,
                            'lot_name': False,
                        })
                        _logger.info("🟡 [STOCK PICKING] ✅ Write ejecutado exitosamente")
                        
                        # Forzar commit
                        self.env.cr.commit()
                        _logger.info("🟡 [STOCK PICKING] ✅ Commit ejecutado")
                        
                        # Verificar que se limpiaron
                        move_lines_verificacion = self.env['stock.move.line'].search([
                            ('picking_id', '=', picking.id)
                        ])
                        _logger.info("🟡 [STOCK PICKING] VERIFICACIÓN - Total líneas: %s", len(move_lines_verificacion))
                        for ml in move_lines_verificacion:
                            _logger.info("🟡 [STOCK PICKING] VERIFICACIÓN - Move Line ID: %s, Lote después: %s", 
                                        ml.id, ml.lot_id.name if ml.lot_id else '✅ VACÍO')
                    except Exception as e:
                        _logger.error("🟡 [STOCK PICKING] ❌ ERROR al limpiar lotes: %s", str(e))
                        _logger.exception("🟡 [STOCK PICKING] Traceback completo:")
                else:
                    _logger.warning("🟡 [STOCK PICKING] ⚠️ No se encontraron move_lines para limpiar")
            else:
                _logger.info("🟡 [STOCK PICKING] ⏭️ Picking NO viene de Sale Order - saltando limpieza de lotes")
        
        _logger.info("🟡 [STOCK PICKING] _action_assign() FINALIZADO")
        _logger.info("="*80)
        return res
    
    def button_validate(self):
        """Validar holds antes de validar el picking"""
        _logger.info("🔴 [STOCK PICKING] button_validate() iniciando para: %s", self.mapped('name'))
        
        for picking in self:
            if picking.picking_type_code == 'outgoing':
                # ✅ CORRECCIÓN: Obtener la empresa del picking
                company_id = picking.company_id.id if picking.company_id else self.env.company.id
                _logger.info("🔴 [STOCK PICKING] Validando con empresa: %s (ID: %s)", 
                            picking.company_id.name if picking.company_id else 'N/A',
                            company_id)
                
                for move_line in picking.move_line_ids:
                    if move_line.lot_id:
                        _logger.info("🔴 [STOCK PICKING] Verificando lote: %s para move_line: %s", 
                                    move_line.lot_id.name, move_line.id)
                        
                        # ✅ CORRECCIÓN: Verificar si el lote tiene hold EN LA EMPRESA CORRECTA
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', move_line.lot_id.id),
                            ('location_id', '=', move_line.location_id.id),
                            ('company_id', '=', company_id),
                            ('x_tiene_hold', '=', True),
                        ], limit=1)
                        
                        if quant and quant.x_hold_activo_id:
                            # Validar que el cliente coincida
                            if picking.partner_id != quant.x_hold_activo_id.partner_id:
                                _logger.warning("🔴 [STOCK PICKING] ⚠️ Hold encontrado para cliente diferente")
                                raise UserError(
                                    f"🔒 NO PUEDE VALIDAR ESTA ENTREGA\n\n"
                                    f"El lote '{move_line.lot_id.name}' está RESERVADO para:\n"
                                    f"👤 {quant.x_hold_para}\n"
                                    f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                                    f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                                    f"❌ Esta entrega es para '{picking.partner_id.name}'"
                                )
        
        result = super(StockPicking, self).button_validate()
        _logger.info("🔴 [STOCK PICKING] button_validate() completado")
        return result```

## ./models/stock_quant.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Campos relacionados del lote
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', string='Tipo', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', string='Atado', readonly=True)
    x_grupo = fields.Many2many(related='lot_id.x_grupo', string='Grupo', readonly=True)
    x_pedimento = fields.Char(related='lot_id.x_pedimento', string='Pedimento', readonly=True)
    x_contenedor = fields.Char(related='lot_id.x_contenedor', string='Contenedor', readonly=True)
    x_referencia_proveedor = fields.Char(related='lot_id.x_referencia_proveedor', string='Ref. Proveedor', readonly=True)
    x_fotografia_principal = fields.Binary(related='lot_id.x_fotografia_principal', readonly=True)
    x_cantidad_fotos = fields.Integer(related='lot_id.x_cantidad_fotos', readonly=True)
    x_detalles_placa = fields.Text(related='lot_id.x_detalles_placa', string='Detalles', readonly=True)
    
    # Campos computados de estado
    x_esta_reservado = fields.Boolean(
        string='Reservado (Sistema)',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está reservado por el sistema de entregas'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está en una orden de entrega confirmada'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=True,
        help='Indica si la placa tiene detalles especiales registrados'
    )
    
    # CAMPOS PARA HOLD MANUAL - RELACIÓN INVERSA
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
    )
    
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=True,
        help='Indica si el lote tiene una reserva manual activa'
    )
    
    x_hold_activo_id = fields.Many2one(
        'stock.lot.hold',
        string='Hold Activo',
        compute='_compute_estado_hold',
        store=True,
        help='Hold activo actualmente en este quant'
    )
    
    x_hold_para = fields.Char(
        string='Reservado Para',
        compute='_compute_estado_hold',
        store=True,
        help='Cliente para quien está reservado'
    )
    
    x_hold_expira = fields.Datetime(
        string='Expira',
        compute='_compute_estado_hold',
        store=True,
        help='Fecha de expiración del hold'
    )
    
    x_hold_dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_estado_hold',
        help='Días hábiles restantes del hold'
    )
    
    # Campo de estado visual combinado
    estado_placa = fields.Char(
        string='Estado Placa',
        compute='_compute_estado_placa',
        help='Estado visual de la placa (JSON para widget)'
    )

    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si la placa tiene detalles especiales"""
        for quant in self:
            quant.x_tiene_detalles = bool(quant.x_detalles_placa and quant.x_detalles_placa.strip())

    @api.depends('x_hold_ids.estado', 'x_hold_ids.fecha_expiracion')
    def _compute_estado_hold(self):
        """Computar el estado del hold manual"""
        for quant in self:
            hold_activo = quant.x_hold_ids.filtered(lambda h: h.estado == 'activo')
            if hold_activo:
                # Tomar el más reciente si hay múltiples
                hold_activo = hold_activo[0]
                quant.x_tiene_hold = True
                quant.x_hold_activo_id = hold_activo.id
                quant.x_hold_para = hold_activo.partner_id.name
                quant.x_hold_expira = hold_activo.fecha_expiracion
                quant.x_hold_dias_restantes = hold_activo.dias_restantes
            else:
                quant.x_tiene_hold = False
                quant.x_hold_activo_id = False
                quant.x_hold_para = False
                quant.x_hold_expira = False
                quant.x_hold_dias_restantes = 0

    @api.depends('reserved_quantity', 'quantity', 'lot_id')
    def _compute_estado_reserva(self):
        """Computar si el lote está reservado por el sistema de entregas"""
        for quant in self:
            # Solo verificar si hay cantidad reservada por el sistema
            quant.x_esta_reservado = quant.reserved_quantity > 0
            
            # Verificar si está en una orden de entrega confirmada
            quant.x_en_orden_entrega = False
            
            if quant.lot_id and quant.x_esta_reservado:
                # Buscar move lines con este lote en estado asignado
                move_lines = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('location_id', '=', quant.location_id.id),
                    ('state', 'in', ['assigned', 'partially_available']),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                ], limit=1)
                
                if move_lines:
                    quant.x_en_orden_entrega = True

    @api.depends(
        'x_esta_reservado',
        'x_en_orden_entrega', 
        'x_tiene_detalles',
        'x_detalles_placa',
        'x_tiene_hold',
        'x_hold_para',
        'x_hold_dias_restantes'
    )
    def _compute_estado_placa(self):
        """Generar JSON con los estados para el widget visual"""
        for quant in self:
            estados = []
            
            # HOLD MANUAL (prioridad más alta)
            if quant.x_tiene_hold:
                dias_texto = f'{quant.x_hold_dias_restantes} días hábiles' if quant.x_hold_dias_restantes != 1 else '1 día hábil'
                estados.append({
                    'type': 'hold',
                    'icon': '🔒',
                    'label': f'HOLD para {quant.x_hold_para}',
                    'detail': f'Expira en {dias_texto}',
                    'class': 'text-warning' if quant.x_hold_dias_restantes <= 2 else 'text-info'
                })
            
            # RESERVA DEL SISTEMA (solo si no tiene hold manual)
            elif quant.x_esta_reservado and quant.x_en_orden_entrega:
                # Obtener el documento de referencia
                move_line = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('location_id', '=', quant.location_id.id),
                    ('state', 'in', ['assigned', 'partially_available']),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                ], limit=1)
                
                if move_line:
                    estados.append({
                        'type': 'delivery',
                        'icon': '📦',
                        'label': 'En Orden de Entrega',
                        'detail': f'Doc: {move_line.picking_id.name}',
                        'class': 'text-primary'
                    })
            
            # DETALLES ESPECIALES
            if quant.x_tiene_detalles:
                detalles_cortos = quant.x_detalles_placa[:30] + '...' if len(quant.x_detalles_placa) > 30 else quant.x_detalles_placa
                estados.append({
                    'type': 'details',
                    'icon': '⚠️',
                    'label': 'Detalles Especiales',
                    'detail': detalles_cortos,
                    'class': 'text-danger'
                })
            
            quant.estado_placa = json.dumps(estados) if estados else False

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Agregar Fotografía al Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }

    def action_view_lot_photos(self):
        """Ver las fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Fotografías del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'tree,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }

    # ACCIONES PARA HOLD
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        # Verificar si ya tiene hold activo
        if self.x_tiene_hold:
            dias_texto = f'{self.x_hold_dias_restantes} días hábiles' if self.x_hold_dias_restantes != 1 else '1 día hábil'
            raise models.UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {dias_texto}.'
            )
        
        return {
            'name': f'Reservar Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quant_id': self.id,
                'default_lot_id': self.lot_id.id,
            }
        }

    def action_ver_hold(self):
        """Ver detalles del hold activo"""
        self.ensure_one()
        if not self.x_hold_activo_id:
            raise models.UserError('Este lote no tiene una reserva activa.')
        
        return {
            'name': f'Reserva del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold',
            'view_mode': 'form',
            'res_id': self.x_hold_activo_id.id,
            'target': 'new',
        }

    def action_cancelar_hold(self):
        """Cancelar el hold activo"""
        self.ensure_one()
        if not self.x_hold_activo_id:
            raise models.UserError('Este lote no tiene una reserva activa.')
        
        self.x_hold_activo_id.action_cancelar_hold()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Éxito!',
                'message': f'Reserva cancelada para el lote {self.lot_id.name}',
                'type': 'success',
                'sticky': False,
            } 
        }

    @api.model
    def get_current_user_info(self):
        """Obtener información del usuario actual"""
        return {
            'id': self.env.user.id,
            'name': self.env.user.name
        }
    
    @api.model
    def sync_cart_to_session(self, items):
        """Sincronizar carrito desde frontend a BD"""
        cart_model = self.env['shopping.cart']
        cart_model.clear_cart()
        
        for item in items:
            cart_model.add_to_cart(
                quant_id=item['id'],
                lot_id=item['lot_id'],
                product_id=item['product_id'],
                quantity=item['quantity'],
                location_name=item['location_name']
            )
        
        return {'success': True}
    
    @api.model
    def create_holds_from_cart(self, partner_id=None, project_id=None, architect_id=None, 
                                selected_lots=None, notes=None, currency_code='USD', product_prices=None):
        """
        Crear holds múltiples desde el carrito con información de precios
        
        Args:
            partner_id: ID del cliente
            project_id: ID del proyecto
            architect_id: ID del arquitecto
            selected_lots: Lista de IDs de quants a apartar
            notes: Notas adicionales
            currency_code: Código de la divisa (USD/MXN)
            product_prices: Diccionario {product_id: precio}
        """
        if not partner_id or not selected_lots:
            return {
                'success': 0, 
                'errors': 1, 
                'holds': [], 
                'failed': [{'error': 'Parámetros inválidos'}]
            }
        
        if not project_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un proyecto'}]
            }
        
        if not architect_id:
            return {
                'success': 0,
                'errors': 1,
                'holds': [],
                'failed': [{'error': 'Debe seleccionar un arquitecto'}]
            }
        
        holds_created = []
        errors = []
        
        from datetime import timedelta
        fecha_inicio = fields.Datetime.now()
        fecha_actual = fecha_inicio
        dias_agregados = 0
        
        # Calcular fecha de expiración (5 días hábiles)
        while dias_agregados < 5:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:
                dias_agregados += 1
        
        fecha_expiracion = fecha_actual
        
        # Agregar información de precios a las notas
        notes_with_prices = notes or ''
        if product_prices:
            notes_with_prices += f'\n\n=== PRECIOS ({currency_code}) ===\n'
            for product_id_str, price in product_prices.items():
                try:
                    product = self.env['product.product'].browse(int(product_id_str))
                    if product.exists():
                        notes_with_prices += f'• {product.display_name}: {price:.2f} {currency_code}/m²\n'
                except Exception as e:
                    _logger.warning(f"Error agregando precio para producto {product_id_str}: {str(e)}")
        
        # Crear holds para cada lote
        for quant_id in selected_lots:
            quant = self.browse(quant_id)
            
            if not quant.exists() or not quant.lot_id:
                errors.append({
                    'quant_id': quant_id, 
                    'error': 'Quant no válido o sin lote'
                })
                continue
            
            if quant.x_tiene_hold:
                errors.append({
                    'lot_name': quant.lot_id.name, 
                    'error': f'Ya apartado para {quant.x_hold_para}'
                })
                continue
            
            try:
                hold = self.env['stock.lot.hold'].create({
                    'lot_id': quant.lot_id.id,
                    'quant_id': quant.id,
                    'partner_id': partner_id,
                    'user_id': self.env.user.id,
                    'project_id': project_id,
                    'arquitecto_id': architect_id,
                    'fecha_inicio': fecha_inicio,
                    'fecha_expiracion': fecha_expiracion,
                    'notas': notes_with_prices,
                })
                
                holds_created.append({
                    'lot_name': quant.lot_id.name,
                    'hold_id': hold.id,
                    'expira': hold.fecha_expiracion.strftime('%d/%m/%Y %H:%M')
                })
            except Exception as e:
                errors.append({
                    'lot_name': quant.lot_id.name, 
                    'error': str(e)
                })
        
        # Limpiar carrito después de crear holds exitosamente
        if holds_created:
            try:
                self.env['shopping.cart'].clear_cart()
            except Exception as e:
                _logger.warning(f"Error al limpiar carrito: {str(e)}")
        
        return {
            'success': len(holds_created),
            'errors': len(errors),
            'holds': holds_created,
            'failed': errors
        }

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, qty=None):
        """
        🔑 OVERRIDE CRÍTICO: Este método es llamado por Odoo para SELECCIONAR qué quants usar.
        
        Aquí es donde debemos filtrar los lotes con holds ANTES de que sean asignados.
        
        Este método se ejecuta ANTES de _get_available_quantity y es el lugar correcto
        para filtrar quants basándonos en holds.
        
        Parámetros Odoo 18:
        - qty: Cantidad requerida (nuevo en Odoo 18)
        """
        _logger.info("🟢" * 50)
        _logger.info("🟢 [_GATHER] Iniciando _gather")
        _logger.info("🟢 [_GATHER] Product: %s", product_id.name if product_id else 'N/A')
        _logger.info("🟢 [_GATHER] Location: %s", location_id.name if location_id else 'N/A')
        _logger.info("🟢 [_GATHER] Lot: %s", lot_id.name if lot_id else 'N/A')
        _logger.info("🟢 [_GATHER] Qty: %s", qty)
        
        # Llamar al método original con todos los parámetros
        quants = super(StockQuant, self)._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id, 
            owner_id=owner_id, strict=strict, qty=qty
        )
        
        _logger.info("🟢 [_GATHER] Quants originales encontrados: %s", len(quants))
        
        # Si no hay cliente permitido en contexto, retornar todos los quants
        cliente_permitido_id = self._context.get('allowed_partner_id')
        
        if not cliente_permitido_id:
            _logger.info("🟢 [_GATHER] ⚠️ No hay allowed_partner_id en contexto")
            _logger.info("🟢 [_GATHER] Retornando todos los quants sin filtrar")
            _logger.info("🟢" * 50)
            return quants
        
        _logger.info("🟢 [_GATHER] ✅ Cliente permitido en contexto: ID %s", cliente_permitido_id)
        
        # Filtrar quants que tienen hold para OTRO cliente
        quants_validos = self.env['stock.quant']
        
        for quant in quants:
            lot_name = quant.lot_id.name if quant.lot_id else 'Sin lote'
            tiene_hold = quant.x_tiene_hold
            
            _logger.info("🟢 [_GATHER] ─────────────────────────────────────")
            _logger.info("🟢 [_GATHER] Analizando Quant ID: %s, Lote: %s", quant.id, lot_name)
            _logger.info("🟢 [_GATHER] Cantidad: %.2f, Tiene hold: %s", quant.quantity, tiene_hold)
            
            # Si no tiene hold, es válido
            if not tiene_hold:
                _logger.info("🟢 [_GATHER] ✅ SIN HOLD - Agregando a lista válida")
                quants_validos |= quant
                continue
            
            # Si tiene hold, verificar que sea para este cliente
            if quant.x_hold_activo_id:
                hold_partner_id = quant.x_hold_activo_id.partner_id.id
                hold_partner_name = quant.x_hold_activo_id.partner_id.name
                
                _logger.info("🟢 [_GATHER] Hold activo encontrado:")
                _logger.info("🟢 [_GATHER]   - Partner del hold: %s (ID: %s)", hold_partner_name, hold_partner_id)
                _logger.info("🟢 [_GATHER]   - Partner permitido: ID %s", cliente_permitido_id)
                
                if hold_partner_id == cliente_permitido_id:
                    _logger.info("🟢 [_GATHER] ✅ HOLD PARA CLIENTE PERMITIDO - Agregando a lista válida")
                    quants_validos |= quant
                else:
                    _logger.warning("🟢 [_GATHER] ❌ HOLD PARA OTRO CLIENTE - NO agregando")
                    _logger.warning("🟢 [_GATHER]    Este quant NO debe ser usado por FIFO/LIFO")
            else:
                _logger.warning("🟢 [_GATHER] ⚠️ Tiene hold pero sin x_hold_activo_id - NO agregando")
        
        _logger.info("🟢 [_GATHER] ═════════════════════════════════════════")
        _logger.info("🟢 [_GATHER] RESUMEN:")
        _logger.info("🟢 [_GATHER] Quants originales: %s", len(quants))
        _logger.info("🟢 [_GATHER] Quants válidos después del filtro: %s", len(quants_validos))
        _logger.info("🟢 [_GATHER] _gather() FINALIZADO")
        _logger.info("🟢" * 50)
        
        return quants_validos```

## ./static/src/js/image_gallery_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImageGalleryWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            images: [],
            currentIndex: 0,
            showModal: false,
        });
        this.loadImages();
    }

    async loadImages() {
        if (this.props.value) {
            const lotId = this.props.value;
            const images = await this.orm.searchRead(
                "stock.lot.image",
                [["lot_id", "=", lotId]],
                ["id", "name", "image", "sequence"],
                { order: "sequence, id" }
            );
            this.state.images = images;
        }
    }

    openGallery(index) {
        this.state.currentIndex = index;
        this.state.showModal = true;
    }

    closeGallery() {
        this.state.showModal = false;
    }

    nextImage() {
        if (this.state.currentIndex < this.state.images.length - 1) {
            this.state.currentIndex++;
        }
    }

    prevImage() {
        if (this.state.currentIndex > 0) {
            this.state.currentIndex--;
        }
    }

    getImageUrl(imageId) {
        return `/web/image/stock.lot.image/${imageId}/image`;
    }
}

ImageGalleryWidget.template = "stock_lot_dimensions.ImageGalleryWidget";

registry.category("fields").add("image_gallery", {
    component: ImageGalleryWidget,
});
```

## ./static/src/js/image_preview_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImagePreviewWidget extends Component {
    setup() {
        this.state = useState({
            showModal: false,
        });
    }

    get imageUrl() {
        if (!this.props.value) {
            return null;
        }
        // El valor viene como base64, lo convertimos a data URL
        return `data:image/png;base64,${this.props.value}`;
    }

    openPreview(ev) {
        // Prevenir que se abra el registro
        ev.stopPropagation();
        ev.preventDefault();
        
        if (this.props.value) {
            this.state.showModal = true;
        }
    }

    closePreview() {
        this.state.showModal = false;
    }
}

ImagePreviewWidget.template = "stock_lot_dimensions.ImagePreviewWidget";

registry.category("fields").add("image_preview_clickable", {
    component: ImagePreviewWidget,
});```

## ./static/src/js/status_icons_widget.js
```js
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StatusIconsWidget extends Component {
    static template = "stock_lot_dimensions.StatusIconsWidget";
    static supportedTypes = ["char"];

    setup() {
        this.notification = useService("notification");
    }

    get estados() {
        const data = this.props.record.data;
        return {
            reservado: data.x_esta_reservado || false,
            entrega: data.x_en_orden_entrega || false,
            detalles: data.x_tiene_detalles || false,
            textoDetalles: data.x_detalles_placa || 'Sin detalles'
        };
    }

    mostrarDetalles(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.notification.add(this.estados.textoDetalles, {
            title: "Detalles de la Placa",
            type: "info",
        });
    }
}

registry.category("fields").add("status_icons", {
    component: StatusIconsWidget,
});```

## ./static/src/xml/image_gallery.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.ImageGalleryWidget" owl="1">
        <div class="image-gallery-container">
            <div class="image-gallery-thumbnails">
                <t t-foreach="state.images" t-as="image" t-key="image.id">
                    <img 
                        t-att-src="getImageUrl(image.id)" 
                        t-att-alt="image.name"
                        class="image-gallery-thumbnail"
                        t-on-click="() => openGallery(image_index)"
                    />
                </t>
            </div>
            
            <t t-if="state.showModal">
                <div class="image-gallery-modal" t-on-click="closeGallery">
                    <div class="image-gallery-content" t-on-click.stop="">
                        <button class="image-gallery-close" t-on-click="closeGallery">×</button>
                        <img 
                            t-att-src="getImageUrl(state.images[state.currentIndex].id)" 
                            t-att-alt="state.images[state.currentIndex].name"
                            class="image-gallery-main"
                        />
                        <div class="image-gallery-controls">
                            <button 
                                class="image-gallery-btn" 
                                t-on-click="prevImage"
                                t-att-disabled="state.currentIndex === 0"
                            >‹</button>
                            <button 
                                class="image-gallery-btn" 
                                t-on-click="nextImage"
                                t-att-disabled="state.currentIndex === state.images.length - 1"
                            >›</button>
                        </div>
                    </div>
                </div>
            </t>
        </div>
    </t>
</templates>
```

## ./static/src/xml/image_preview_widget.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.ImagePreviewWidget" owl="1">
        <div class="image-preview-wrapper" t-if="imageUrl">
            <img 
                t-att-src="imageUrl" 
                class="image-preview-thumbnail"
                t-on-click="openPreview"
                alt="Fotografía"
            />
            
            <t t-if="state.showModal">
                <div class="image-preview-modal" t-on-click="closePreview">
                    <div class="image-preview-content" t-on-click.stop="">
                        <button class="image-preview-close" t-on-click="closePreview">×</button>
                        <img 
                            t-att-src="imageUrl" 
                            class="image-preview-full"
                            alt="Fotografía"
                        />
                    </div>
                </div>
            </t>
        </div>
        <div t-else="" class="image-preview-placeholder">
            <i class="fa fa-picture-o"></i>
        </div>
    </t>
</templates>```

## ./static/src/xml/status_icons_widget.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="stock_lot_dimensions.StatusIconsWidget" owl="1">
        <div class="d-flex" style="gap: 6px; align-items: center;">
            <t t-if="estados.reservado">
                <span class="badge bg-success" title="Reservado" style="font-size: 0.75rem;">
                    <i class="fa fa-hand-paper-o"/> Reservado
                </span>
            </t>
            
            <t t-if="estados.entrega">
                <span class="badge bg-info" title="En Orden de Entrega" style="font-size: 0.75rem;">
                    <i class="fa fa-shopping-cart"/> En Entrega
                </span>
            </t>
            
            <t t-if="estados.detalles">
                <button class="btn btn-sm btn-warning" 
                        t-on-click="mostrarDetalles"
                        style="padding: 2px 6px; font-size: 0.75rem;">
                    <i class="fa fa-info-circle"/> Detalles
                </button>
            </t>
            
            <t t-if="!estados.reservado and !estados.entrega and !estados.detalles">
                <span class="text-muted">—</span>
            </t>
        </div>
    </t>
</templates>```

## ./views/project_project_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_project_project_form_inherit_marmol" model="ir.ui.view">
        <field name="name">project.project.form.inherit.marmol</field>
        <field name="model">project.project</field>
        <field name="inherit_id" ref="project.edit_project"/>
        <field name="arch" type="xml">
            <field name="name" position="after">
                <field name="x_es_proyecto_marmol"/>
            </field>
        </field>
    </record>

    <record id="action_proyectos_marmol" model="ir.actions.act_window">
        <field name="name">Proyectos de Mármol</field>
        <field name="res_model">project.project</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('x_es_proyecto_marmol', '=', True)]</field>
        <field name="context">{'default_x_es_proyecto_marmol': True}</field>
    </record>

    <menuitem id="menu_proyectos_marmol"
              name="Proyectos de Mármol"
              parent="stock.menu_stock_config_settings"
              action="action_proyectos_marmol"
              sequence="52"/>
</odoo>```

## ./views/res_partner_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_inherit_arquitecto" model="ir.ui.view">
        <field name="name">res.partner.form.inherit.arquitecto</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <field name="category_id" position="after">
                <field name="x_es_arquitecto"/>
            </field>
        </field>
    </record>

    <record id="action_arquitectos" model="ir.actions.act_window">
        <field name="name">Arquitectos</field>
        <field name="res_model">res.partner</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('x_es_arquitecto', '=', True)]</field>
        <field name="context">{'default_x_es_arquitecto': True, 'default_company_type': 'person'}</field>
    </record>

    <menuitem id="menu_arquitectos"
              name="Arquitectos"
              parent="stock.menu_stock_config_settings"
              action="action_arquitectos"
              sequence="51"/>
</odoo>```

## ./views/stock_lot_group_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista Tree de Grupos -->
    <record id="view_stock_lot_group_tree" model="ir.ui.view">
        <field name="name">stock.lot.group.tree</field>
        <field name="model">stock.lot.group</field>
        <field name="arch" type="xml">
            <list string="Grupos de Lotes">
                <field name="name"/>
                <field name="active"/>
            </list>
        </field>
    </record>

    <!-- Vista Form de Grupos -->
    <record id="view_stock_lot_group_form" model="ir.ui.view">
        <field name="name">stock.lot.group.form</field>
        <field name="model">stock.lot.group</field>
        <field name="arch" type="xml">
            <form string="Grupo de Lote">
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="color" widget="color_picker"/>
                        <field name="active"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Acción -->
    <record id="action_stock_lot_group" model="ir.actions.act_window">
        <field name="name">Grupos de Lotes</field>
        <field name="res_model">stock.lot.group</field>
        <field name="view_mode">list,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Crear un nuevo grupo/etiqueta
            </p>
        </field>
    </record>

    <!-- Menú -->
    <menuitem id="menu_stock_lot_group"
              name="Grupos de Productos"
              parent="stock.menu_stock_config_settings"
              action="action_stock_lot_group"
              sequence="50"/>
</odoo>```

## ./views/stock_lot_hold_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_hold_tree" model="ir.ui.view">
        <field name="name">stock.lot.hold.tree</field>
        <field name="model">stock.lot.hold</field>
        <field name="arch" type="xml">
            <list string="Reservas de Lotes">
                <field name="lot_id"/>
                <field name="producto_id"/>
                <field name="partner_id"/>
                <field name="user_id"/>
                <field name="project_id"/>
                <field name="arquitecto_id"/>
                <field name="fecha_inicio"/>
                <field name="fecha_expiracion"/>
                <field name="dias_restantes" 
                       decoration-danger="dias_restantes &lt;= 3"
                       decoration-warning="dias_restantes &lt;= 5 and dias_restantes &gt; 3"/>
                <field name="estado" 
                       decoration-success="estado == 'activo'"
                       decoration-danger="estado == 'expirado'"
                       decoration-muted="estado == 'cancelado'"/>
            </list>
        </field>
    </record>

    <record id="view_stock_lot_hold_form" model="ir.ui.view">
        <field name="name">stock.lot.hold.form</field>
        <field name="model">stock.lot.hold</field>
        <field name="arch" type="xml">
            <form string="Reserva de Lote">
                <header>
                    <button name="action_renovar_hold" 
                            string="Renovar Reserva" 
                            type="object" 
                            class="btn-primary"
                            invisible="estado != 'activo'"/>
                    <button name="action_cancelar_hold" 
                            string="Cancelar Reserva" 
                            type="object" 
                            class="btn-warning"
                            confirm="¿Está seguro de cancelar esta reserva?"
                            invisible="estado != 'activo'"/>
                    <field name="estado" widget="statusbar"/>
                </header>
                <sheet>
                    <group>
                        <group string="Información del Lote">
                            <field name="lot_id"/>
                            <field name="producto_id"/>
                            <field name="ubicacion_id"/>
                        </group>
                        <group string="Información de Reserva">
                            <field name="user_id"/>
                            <field name="partner_id"/>
                            <field name="project_id"/>
                            <field name="arquitecto_id"/>
                        </group>
                    </group>
                    <group>
                        <group string="Fechas">
                            <field name="fecha_inicio"/>
                            <field name="fecha_expiracion"/>
                            <field name="dias_restantes"/>
                        </group>
                        <group string="Notas">
                            <field name="notas" nolabel="1"/>
                        </group>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_stock_lot_hold" model="ir.actions.act_window">
        <field name="name">Reservas de Lotes</field>
        <field name="res_model">stock.lot.hold</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="menu_stock_lot_hold"
              name="Reservas de Lotes"
              parent="stock.menu_stock_warehouse_mgmt"
              action="action_stock_lot_hold"
              sequence="100"/>
</odoo>```

## ./views/stock_lot_hold_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_hold_wizard_form" model="ir.ui.view">
        <field name="name">stock.lot.hold.wizard.form</field>
        <field name="model">stock.lot.hold.wizard</field>
        <field name="arch" type="xml">
            <form string="Reservar Lote">
                <group>
                    <group string="Información del Lote">
                        <field name="lot_id" readonly="1"/>
                        <field name="producto_id" readonly="1"/>
                        <field name="ubicacion_id" readonly="1"/>
                        <field name="cantidad_disponible" readonly="1"/>
                    </group>
                    
                    <group string="Dimensiones">
                        <field name="x_grosor" readonly="1"/>
                        <field name="x_alto" readonly="1"/>
                        <field name="x_ancho" readonly="1"/>
                        <field name="x_bloque" readonly="1"/>
                        <field name="x_atado" readonly="1"/>
                    </group>
                </group>
                
                <group>
                    <group string="Información de Reserva">
                        <field name="user_id"/>
                        <field name="partner_id" options="{'no_open': True}" context="{'default_customer_rank': 1}"/>
                        <field name="project_id" invisible="project_name"/>
                        <field name="project_name" placeholder="O ingrese nuevo proyecto..." invisible="project_id"/>
                        <field name="arquitecto_id" invisible="arquitecto_name"/>
                        <field name="arquitecto_name" placeholder="O ingrese nuevo arquitecto..." invisible="arquitecto_id"/>
                        <field name="fecha_expiracion" readonly="1"/>
                    </group>
                    
                    <group string="Notas">
                        <field name="notas" 
                               nolabel="1" 
                               placeholder="Ej: Para proyecto X, Cotización Y, etc."/>
                    </group>
                </group>
                
                <div class="alert alert-info" role="alert">
                    <strong>Campos obligatorios:</strong> Vendedor, Cliente, Proyecto y Arquitecto son requeridos para crear la reserva.
                    La reserva expirará automáticamente en 10 días.
                </div>
                
                <footer>
                    <button name="action_crear_hold" 
                            string="Crear Reserva" 
                            type="object" 
                            class="btn-primary"/>
                    <button string="Cancelar" 
                            class="btn-secondary" 
                            special="cancel"/>
                </footer>
                
                <field name="quant_id" invisible="1"/>
            </form>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_image_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_stock_lot_image_wizard_form" model="ir.ui.view">
        <field name="name">stock.lot.image.wizard.form</field>
        <field name="model">stock.lot.image.wizard</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="lot_id" readonly="1" class="oe_inline"/>
                        </h1>
                    </div>
                    
                    <group>
                        <group>
                            <field name="name" placeholder="Ej: Foto frontal, Foto lateral, etc."/>
                            <field name="sequence"/>
                        </group>
                        <group>
                            <field name="notas" placeholder="Notas adicionales sobre esta fotografía..."/>
                        </group>
                    </group>
                    
                    <group string="Imagen">
                        <field name="image" 
                               widget="image" 
                               class="oe_avatar" 
                               options="{'preview_image': 'image', 'size': [400, 400]}"/>
                    </group>
                </sheet>
                <footer>
                    <button string="Guardar y Cerrar" 
                            name="action_save_image" 
                            type="object" 
                            class="btn-primary"/>
                    <button string="Cancelar" 
                            class="btn-secondary" 
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista de formulario mejorada del lote -->
    <record id="view_production_lot_form_inherit" model="ir.ui.view">
        <field name="name">stock.lot.form.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_form"/>
        <field name="arch" type="xml">
            <!-- Agregar botón smartbutton para ver fotografías -->
            <div name="button_box" position="inside">
                <button class="oe_stat_button" 
                        type="object" 
                        name="action_view_images" 
                        icon="fa-camera"
                        invisible="x_cantidad_fotos == 0">
                    <field name="x_cantidad_fotos" widget="statinfo" string="Fotos"/>
                </button>
            </div>

            <!-- Campos invisibles computados -->
            <field name="product_id" position="after">
                <field name="x_tiene_fotografias" invisible="1"/>
                <field name="x_fotografia_principal" invisible="1"/>
            </field>

            <!-- Sección de Dimensiones y Características -->
            <xpath expr="//group[@name='main_group']" position="after">
                <notebook>
                    <page string="Dimensiones y Características" name="dimensions">
                        <group>
                            <group string="Dimensiones" name="dimensions_group">
                                <field name="x_grosor" 
                                       widget="float" 
                                       placeholder="0.00"/>
                                <field name="x_alto" 
                                       widget="float" 
                                       placeholder="0.0000"/>
                                <field name="x_ancho" 
                                       widget="float" 
                                       placeholder="0.0000"/>
                            </group>

                            <group string="Características" name="characteristics_group">
                                <field name="x_tipo" 
                                       placeholder="Selecciona tipo..."/>
                                <field name="x_bloque" 
                                       placeholder="Identificación del bloque"/>
                                <field name="x_atado" 
                                    placeholder="Identificación del atado"/>
                                <field name="x_grupo" 
                                    widget="many2many_tags" 
                                    options="{'color_field': 'color', 'no_create_edit': True}"
                                    placeholder="Selecciona grupos..."/>
                                <field name="x_pedimento" 
                                    placeholder="Número de pedimento"/>
                                <field name="x_contenedor" 
                                    placeholder="Número de contenedor"/>
                                <field name="x_referencia_proveedor" 
                                    placeholder="Referencia del proveedor"/>
                            </group>
                        </group>

                        <group string="Detalles Adicionales" name="details_group">
                            <field name="x_detalles_placa" 
                                   placeholder="Detalles especiales: rota, barreno, release, etc."
                                   nolabel="1"/>
                        </group>
                    </page>

                    <page string="Fotografías" name="photos" invisible="x_cantidad_fotos == 0">
                        <field name="x_fotografia_ids" 
                               widget="image_gallery" 
                               mode="kanban" 
                               nolabel="1">
                            <kanban class="o_kanban_mobile">
                                <field name="id"/>
                                <field name="name"/>
                                <field name="image"/>
                                <field name="sequence"/>
                                <templates>
                                    <t t-name="kanban-box">
                                        <div class="oe_kanban_global_click o_kanban_record_has_image_fill">
                                            <div class="o_kanban_image">
                                                <img t-att-src="kanban_image('stock.lot.image', 'image', record.id.raw_value)" 
                                                     alt="Foto" 
                                                     class="o_image_64_cover"/>
                                            </div>
                                            <div class="oe_kanban_details">
                                                <strong class="o_kanban_record_title">
                                                    <field name="name"/>
                                                </strong>
                                                <div class="o_kanban_record_subtitle">
                                                    <field name="notas"/>
                                                </div>
                                            </div>
                                        </div>
                                    </t>
                                </templates>
                            </kanban>
                            <form string="Fotografía">
                                <sheet>
                                    <group>
                                        <field name="name"/>
                                        <field name="sequence"/>
                                    </group>
                                    <group>
                                        <field name="image" widget="image" class="oe_avatar"/>
                                    </group>
                                    <group>
                                        <field name="notas" placeholder="Notas adicionales..."/>
                                    </group>
                                </sheet>
                            </form>
                        </field>
                    </page>
                </notebook>
            </xpath>
        </field>
    </record>

    <!-- Vista tree de lotes con dimensiones -->
    <record id="view_production_lot_tree_inherit" model="ir.ui.view">
        <field name="name">stock.lot.tree.inherit.dimensions</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='product_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_tipo" optional="show" string="Tipo"/>
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_atado" optional="show" string="Atado"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento" optional="show" string="Pedimento"/>
                <field name="x_contenedor" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal" 
                       widget="image_preview" 
                       options="{'size': [60, 60]}" 
                       optional="hide"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos"/>
            </xpath>
        </field>
    </record>

</odoo>```

## ./views/stock_move_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Extender vista de líneas de movimiento en recepción -->
    <record id="view_stock_move_line_operation_tree_inherit" model="ir.ui.view">
        <field name="name">stock.move.line.operations.tree.inherit.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_stock_move_line_operation_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <!-- Campo computed para determinar si es recepción -->
                <field name="x_is_incoming" column_invisible="1"/>
                
                <!-- Campos temporales (editables solo en recepciones) -->
                <field name="x_grosor_temp" 
                       optional="show" 
                       string="Grosor (cm)"
                       readonly="not x_is_incoming"/>
                <field name="x_alto_temp" 
                       optional="show" 
                       string="Alto (m)"
                       readonly="not x_is_incoming"/>
                <field name="x_ancho_temp" 
                       optional="show" 
                       string="Ancho (m)"
                       readonly="not x_is_incoming"/>
                <field name="x_tipo_temp" 
                       optional="show" 
                       string="Tipo"
                       readonly="not x_is_incoming"/>
                <field name="x_bloque_temp" 
                       optional="show" 
                       string="Bloque"
                       readonly="not x_is_incoming"/>
                <field name="x_atado_temp" 
                       optional="show" 
                       string="Atado"
                       readonly="not x_is_incoming"/>
                
                <field name="x_grupo_temp" 
                    widget="many2many_tags"
                    optional="show" 
                    string="Grupo"
                    readonly="not x_is_incoming"/>
                <field name="x_pedimento_temp" 
                    optional="show" 
                    string="Pedimento"
                    readonly="not x_is_incoming"/>
                <field name="x_contenedor_temp" 
                    optional="show" 
                    string="Contenedor"
                    readonly="not x_is_incoming"/>
                <field name="x_referencia_proveedor_temp" 
                    optional="show" 
                    string="Ref. Proveedor"
                    readonly="not x_is_incoming"/>
            </xpath>
        </field>
    </record>

    <!-- Vista tree para historial de movimientos con dimensiones del lote -->
    <record id="view_move_line_tree_inherit_dimensions" model="ir.ui.view">
        <field name="name">stock.move.line.tree.inherit.lot.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_move_line_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor_lote" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto_lote" optional="hide" string="Alto (m)"/>
                <field name="x_ancho_lote" optional="hide" string="Ancho (m)"/>
                <field name="x_tipo_lote" optional="show" string="Tipo"/>
                <field name="x_bloque_lote" optional="show" string="Bloque"/>
                <field name="x_atado_lote" optional="show" string="Atado"/>
                <field name="x_grupo_lote" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento_lote" optional="show" string="Pedimento"/>
                <field name="x_contenedor_lote" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor_lote" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal_lote" widget="image_preview" options="{'size': [60, 60]}" optional="hide"/>
                <field name="x_cantidad_fotos_lote" optional="show" string="Fotos"/>
            </xpath>
        </field>
    </record>

    <record id="view_stock_move_operations_form_inherit" model="ir.ui.view">
        <field name="name">stock.move.operations.form.inherit.dimensions</field>
        <field name="model">stock.move</field>
        <field name="inherit_id" ref="stock.view_stock_move_operations"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='move_line_ids']" position="attributes">
                <attribute name="context">{'list_view_ref': 'stock_lot_dimensions.view_stock_move_line_operation_tree_inherit', 'form_view_ref': 'stock_lot_dimensions.view_move_line_mobile_form_inherit', 'default_picking_id': picking_id, 'default_move_id': id, 'default_product_id': product_id, 'default_location_id': location_id, 'default_location_dest_id': location_dest_id, 'default_company_id': company_id, 'active_picking_id': picking_id}</attribute>
            </xpath>
        </field>
    </record>

    <record id="view_move_line_mobile_form_inherit" model="ir.ui.view">
        <field name="name">stock.move.line.mobile.form.inherit.dimensions</field>
        <field name="model">stock.move.line</field>
        <field name="inherit_id" ref="stock.view_move_line_mobile_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_is_incoming" invisible="1"/>
                
                <group string="Dimensiones del Lote" col="2">
                    <field name="x_grosor_temp" 
                           string="Grosor (cm)"
                           readonly="not x_is_incoming"/>
                    <field name="x_alto_temp" 
                           string="Alto (m)"
                           readonly="not x_is_incoming"/>
                    <field name="x_ancho_temp" 
                           string="Ancho (m)"
                           readonly="not x_is_incoming"/>
                    <field name="x_tipo_temp" 
                           string="Tipo"
                           readonly="not x_is_incoming"/>
                    <field name="x_bloque_temp" 
                           string="Bloque"
                           readonly="not x_is_incoming"/>
                    <field name="x_atado_temp" 
                           string="Atado"
                           readonly="not x_is_incoming"/>
                    
                    <field name="x_grupo_temp" 
                        widget="many2many_tags"
                        string="Grupo"
                        readonly="not x_is_incoming"/>
                    <field name="x_pedimento_temp" 
                        string="Pedimento"
                        readonly="not x_is_incoming"/>
                    <field name="x_contenedor_temp" 
                        string="Contenedor"
                        readonly="not x_is_incoming"/>
                    <field name="x_referencia_proveedor_temp" 
                        string="Ref. Proveedor"
                        readonly="not x_is_incoming"/>
                    
                </group>
            </xpath>
            
            <xpath expr="//group[last()]" position="after">
                <group string="Fotografías" invisible="not lot_id">
                    <button name="action_add_photos" 
                            string="Agregar Fotografías" 
                            type="object" 
                            class="btn-primary"
                            invisible="not lot_id"/>
                    <button name="action_view_lot_photos" 
                            string="Ver Fotografías" 
                            type="object" 
                            class="btn-secondary"
                            invisible="not lot_id or not x_cantidad_fotos_lote"/>
                </group>
            </xpath>
        </field>
    </record>
</odoo>```

## ./views/stock_quant_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista tree de ubicaciones con dimensiones y hold -->
    <record id="view_stock_quant_tree_inherit" model="ir.ui.view">
        <field name="name">stock.quant.tree.inherit.dimensions</field>
        <field name="model">stock.quant</field>
        <field name="inherit_id" ref="stock.view_stock_quant_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)"/>
                <field name="x_alto" optional="hide" string="Alto (m)"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)"/>
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_tipo" optional="show" string="Tipo"/>
                <field name="x_atado" optional="show" string="Atado"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo"/>
                <field name="x_pedimento" optional="show" string="Pedimento"/>
                <field name="x_contenedor" optional="show" string="Contenedor"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- NUEVOS CAMPOS DE HOLD -->
                <field name="x_tiene_hold" column_invisible="1"/>
                <field name="x_hold_para" optional="show" string="Hold Para"/>
                <field name="x_hold_dias_restantes" optional="show" string="Días Hold"
                       decoration-danger="x_tiene_hold and x_hold_dias_restantes &lt;= 3"
                       decoration-warning="x_tiene_hold and x_hold_dias_restantes &lt;= 5 and x_hold_dias_restantes &gt; 3"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"/>
            </xpath>
        </field>
    </record>

    <!-- Vista tree editable (para ubicaciones) con botones de hold -->
    <record id="view_stock_quant_tree_editable_inherit" model="ir.ui.view">
        <field name="name">stock.quant.tree.editable.inherit.dimensions</field>
        <field name="model">stock.quant</field>
        <field name="inherit_id" ref="stock.view_stock_quant_tree_editable"/>
        <field name="arch" type="xml">
            <!-- Agregar campos después de lot_id -->
            <xpath expr="//field[@name='lot_id']" position="after">
                <field name="x_grosor" optional="hide" string="Grosor (cm)" readonly="1"/>
                <field name="x_alto" optional="hide" string="Alto (m)" readonly="1"/>
                <field name="x_ancho" optional="hide" string="Ancho (m)" readonly="1"/>
                <field name="x_bloque" optional="show" string="Bloque" readonly="1"/>
                <field name="x_tipo" optional="show" string="Tipo" readonly="1"/>
                <field name="x_atado" optional="show" string="Atado" readonly="1"/>
                <field name="x_grupo" widget="many2many_tags" optional="show" string="Grupo" readonly="1"/>
                <field name="x_pedimento" optional="show" string="Pedimento" readonly="1"/>
                <field name="x_contenedor" optional="show" string="Contenedor" readonly="1"/>
                <field name="x_referencia_proveedor" optional="show" string="Ref. Proveedor" readonly="1"/>
                <field name="x_fotografia_principal" widget="image_preview" options="{'size': [60, 60]}" optional="hide" readonly="1"/>
                <field name="x_cantidad_fotos" optional="show" string="Fotos" readonly="1"/>
                
                <!-- Campos invisibles necesarios para el widget -->
                <field name="x_esta_reservado" column_invisible="1"/>
                <field name="x_en_orden_entrega" column_invisible="1"/>
                <field name="x_tiene_detalles" column_invisible="1"/>
                <field name="x_detalles_placa" column_invisible="1"/>
                
                <!-- NUEVOS CAMPOS DE HOLD -->
                <field name="x_tiene_hold" column_invisible="1"/>
                <field name="x_hold_para" optional="show" string="Hold Para" readonly="1"/>
                <field name="x_hold_dias_restantes" optional="show" string="Días Hold" readonly="1"
                       decoration-danger="x_tiene_hold and x_hold_dias_restantes &lt;= 3"
                       decoration-warning="x_tiene_hold and x_hold_dias_restantes &lt;= 5 and x_hold_dias_restantes &gt; 3"/>
                
                <!-- Columna de estado con iconos -->
                <field name="estado_placa" 
                       string="Estado" 
                       widget="status_icons" 
                       nolabel="1"
                       optional="show"
                       readonly="1"/>
            </xpath>
            
            <!-- Agregar botones de HOLD después del botón de Replenishment -->
            <xpath expr="//button[@name='action_view_orderpoints']" position="after">
                <!-- Botón para crear hold (solo si no tiene hold activo) -->
                <button name="action_crear_hold" 
                        string="Reservar Lote" 
                        type="object" 
                        class="btn-link text-success" 
                        icon="fa-lock"
                        invisible="not lot_id or x_tiene_hold"
                        help="Crear reserva manual para este lote"/>
                
                <!-- Botón para ver hold (solo si tiene hold activo) -->
                <button name="action_ver_hold" 
                        string="Ver Reserva" 
                        type="object" 
                        class="btn-link text-info" 
                        icon="fa-eye"
                        invisible="not x_tiene_hold"
                        help="Ver detalles de la reserva activa"/>
                
                <!-- Botón para cancelar hold (solo si tiene hold activo) -->
                <button name="action_cancelar_hold" 
                        string="Cancelar Hold" 
                        type="object" 
                        class="btn-link text-danger" 
                        icon="fa-times"
                        invisible="not x_tiene_hold"
                        confirm="¿Está seguro de cancelar esta reserva?"
                        help="Cancelar la reserva activa"/>
                
                <!-- Botones existentes de fotos -->
                <button name="action_add_photos" 
                        string="Agregar Foto" 
                        type="object" 
                        class="btn-link" 
                        icon="fa-camera"
                        invisible="not lot_id"/>
                <button name="action_view_lot_photos" 
                        string="Ver Fotos" 
                        type="object" 
                        class="btn-link" 
                        icon="fa-picture-o"
                        invisible="not lot_id or not x_cantidad_fotos"/>
            </xpath>
        </field>
    </record>
</odoo>```

## ./wizard/__init__.py
```py
# -*- coding: utf-8 -*-
from . import stock_lot_image_wizard
from . import stock_lot_hold_wizard```

## ./wizard/stock_lot_hold_wizard.py
```py
# ./wizard/stock_lot_hold_wizard.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta

class StockLotHoldWizard(models.TransientModel):
    _name = 'stock.lot.hold.wizard'
    _description = 'Wizard para crear reservas manuales de lotes'

    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        readonly=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True
    )
    
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        related='lot_id.product_id',
        readonly=True
    )
    
    ubicacion_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        related='quant_id.location_id',
        readonly=True
    )
    
    cantidad_disponible = fields.Float(
        string='Cantidad Disponible',
        related='quant_id.available_quantity',
        readonly=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        readonly=True,
        required=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        help='Cliente para quien se reserva el lote'
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        help='Proyecto al que pertenece esta reserva'
    )
    
    project_name = fields.Char(
        string='Nombre del Proyecto',
        help='Ingrese el nombre del nuevo proyecto'
    )
    
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Arquitecto',
        domain=[('x_es_arquitecto', '=', True)],
        help='Arquitecto responsable del proyecto'
    )
    
    arquitecto_name = fields.Char(
        string='Nombre del Arquitecto',
        help='Ingrese el nombre del nuevo arquitecto'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Expira el',
        compute='_compute_fecha_expiracion',
        readonly=True,
        help='Fecha de expiración (5 días hábiles desde hoy)'
    )
    
    notas = fields.Text(
        string='Notas',
        placeholder='Notas adicionales sobre esta reserva...'
    )
    
    x_grosor = fields.Float(related='lot_id.x_grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', readonly=True)

    def _calcular_dias_habiles(self, fecha_inicio, dias_habiles):
        """Calcular fecha de expiración sumando días hábiles"""
        fecha_actual = fecha_inicio
        dias_agregados = 0
        
        while dias_agregados < dias_habiles:
            fecha_actual += timedelta(days=1)
            if fecha_actual.weekday() < 5:  # 0-4 = lunes a viernes
                dias_agregados += 1
        
        return fecha_actual

    @api.depends('create_date')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración: 5 días hábiles desde hoy"""
        for record in self:
            record.fecha_expiracion = self._calcular_dias_habiles(fields.Datetime.now(), 5)

    @api.onchange('project_name')
    def _onchange_project_name(self):
        if self.project_name:
            self.project_id = False

    @api.onchange('arquitecto_name')
    def _onchange_arquitecto_name(self):
        if self.arquitecto_name:
            self.arquitecto_id = False

    @api.constrains('project_id', 'project_name')
    def _check_project(self):
        for record in self:
            if not record.project_id and not record.project_name:
                raise ValidationError('Debe seleccionar un proyecto existente o ingresar el nombre de uno nuevo.')

    @api.constrains('arquitecto_id', 'arquitecto_name')
    def _check_arquitecto(self):
        for record in self:
            if not record.arquitecto_id and not record.arquitecto_name:
                raise ValidationError('Debe seleccionar un arquitecto existente o ingresar el nombre de uno nuevo.')

    def action_crear_hold(self):
        """Crear una nueva reserva manual"""
        self.ensure_one()
        
        # Verificar hold existente
        hold_existente = self.env['stock.lot.hold'].search([
            ('quant_id', '=', self.quant_id.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_existente:
            raise UserError(
                f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} '
                f'que expira el {hold_existente.fecha_expiracion.strftime("%d/%m/%Y")}'
            )
        
        # Obtener o crear proyecto
        project_id = self.project_id.id
        if self.project_name:
            project = self.env['project.project'].create({
                'name': self.project_name,
                'x_es_proyecto_marmol': True,
            })
            project_id = project.id
        
        # Obtener o crear arquitecto
        arquitecto_id = self.arquitecto_id.id
        if self.arquitecto_name:
            arquitecto = self.env['res.partner'].create({
                'name': self.arquitecto_name,
                'x_es_arquitecto': True,
                'company_type': 'person',
            })
            arquitecto_id = arquitecto.id
        
        # 🔑 CALCULAR fecha_expiracion ANTES de crear
        fecha_inicio = fields.Datetime.now()
        fecha_expiracion = self._calcular_dias_habiles(fecha_inicio, 5)
        
        # Crear el hold CON fecha_expiracion
        hold = self.env['stock.lot.hold'].create({
            'lot_id': self.lot_id.id,
            'quant_id': self.quant_id.id,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'project_id': project_id,
            'arquitecto_id': arquitecto_id,
            'fecha_inicio': fecha_inicio,
            'fecha_expiracion': fecha_expiracion,  # 🔑 AGREGAR AQUÍ
            'notas': self.notas,
        })
        
        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Reserva Creada!',
                'message': f'Lote {self.lot_id.name} reservado para {self.partner_id.name} por 5 días hábiles hasta el {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }```

## ./wizard/stock_lot_image_wizard.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLotImageWizard(models.TransientModel):
    _name = 'stock.lot.image.wizard'
    _description = 'Wizard para agregar fotografías a lotes'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        readonly=True
    )
    
    name = fields.Char(
        string='Nombre',
        required=True,
        default='Fotografía'
    )
    
    image = fields.Binary(
        string='Imagen',
        required=True,
        attachment=True
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    
    notas = fields.Text(
        string='Notas',
        placeholder='Notas adicionales sobre esta fotografía...'
    )

    def action_save_image(self):
        """Guardar la imagen y cerrar el wizard"""
        self.ensure_one()
        
        # Crear el registro de imagen
        self.env['stock.lot.image'].create({
            'lot_id': self.lot_id.id,
            'name': self.name,
            'image': self.image,
            'sequence': self.sequence,
            'notas': self.notas,
        })
        
        # Retornar notificación de éxito y cerrar
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Éxito!',
                'message': f'Fotografía agregada correctamente al lote {self.lot_id.name}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }```


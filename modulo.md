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
from . import stock_quant
from . import stock_picking
from . import stock_lot_hold 
from . import sale_order```

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
        Override del método action_confirm para limpiar lotes automáticos
        después de confirmar la orden de venta
        """
        _logger.info("="*80)
        _logger.info("🔵 [SALE ORDER] Iniciando action_confirm() para orden: %s", self.name)
        
        # Primero ejecutar el proceso normal de confirmación
        res = super(SaleOrder, self).action_confirm()
        _logger.info("🔵 [SALE ORDER] Super action_confirm() completado")
        
        # Después de confirmar, limpiar TODOS los lotes asignados automáticamente
        for order in self:
            _logger.info("🔵 [SALE ORDER] Procesando orden: %s", order.name)
            
            # Buscar todos los pickings relacionados con esta orden
            pickings = order.picking_ids
            _logger.info("🔵 [SALE ORDER] Pickings encontrados: %s (%s)", len(pickings), pickings.mapped('name'))
            
            for picking in pickings:
                _logger.info("🔵 [SALE ORDER] Procesando picking: %s (ID: %s)", picking.name, picking.id)
                
                # ============================================
                # SOLUCIÓN DEFINITIVA: ELIMINAR move_lines
                # ============================================
                # En lugar de solo limpiar los lotes, ELIMINAMOS las move_lines
                # Esto fuerza que cuando el usuario abra "Operaciones Detalladas"
                # no haya ninguna línea pre-creada con lotes
                
                move_lines_to_delete = self.env['stock.move.line'].search([
                    ('picking_id', '=', picking.id),
                    ('state', 'not in', ['done', 'cancel'])  # Solo las que no están finalizadas
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
                
                # ============================================
                # Resetear el estado del picking si es necesario
                # ============================================
                if picking.state == 'assigned':
                    _logger.info("🔵 [SALE ORDER] Picking está 'assigned' - cambiando a 'confirmed'")
                    try:
                        picking.write({'state': 'confirmed'})
                        _logger.info("🔵 [SALE ORDER] ✅ Picking state actualizado")
                    except Exception as e:
                        _logger.error("🔵 [SALE ORDER] ⚠️ No se pudo cambiar state del picking: %s", str(e))
                
                # ============================================
                # Resetear los moves también
                # ============================================
                for move in picking.move_ids:
                    if move.state == 'assigned':
                        _logger.info("🔵 [SALE ORDER] Move %s está 'assigned' - reseteando", move.id)
                        try:
                            move.write({'state': 'confirmed'})
                            _logger.info("🔵 [SALE ORDER] ✅ Move %s reseteado", move.id)
                        except Exception as e:
                            _logger.error("🔵 [SALE ORDER] ⚠️ Error reseteando move: %s", str(e))
                
                # ============================================
                # INVALIDAR CACHE para forzar recarga
                # ============================================
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
    
    # x_acabado = fields.Selection([
    #     ('pulido', 'Pulido'),
    #     ('mate', 'Mate'),
    #     ('busardeado', 'Busardeado'),
    #     ('sandblasteado', 'Sandblasteado'),
    #     ('acido_ligero', 'Acido Ligero'),
    #     ('acido_rugoso', 'Acido Rugoso'),
    #     ('cepillado', 'Cepillado'),
    #     ('busardeado_cepillado', 'Busardeado + Cepillado'),
    #     ('sandblasteado_cepillado', 'Sandblasteado + Cepillado'),
    #     ('macheteado', 'Macheteado'),
    #     ('century', 'Century'),
    #     ('apomazado', 'Apomazado'),
    #     ('routeado_nivel1', 'Routeado Nivel 1 (2cm)'),
    #     ('routeado_nivel2', 'Routeado Nivel 2 (4cm)'),
    #     ('routeado_nivel3', 'Routeado Nivel 3 (6cm)'),
    #     ('flameado', 'Flameado'),
    #     ('al_corte', 'Al corte'),
    #     ('natural', 'Natural'),
    #     ('tomboleado', 'Tomboleado'),
    #     ('lino', 'Lino'),
    #     ('raw', 'Raw'),
    #     ('bamboo', 'Bamboo'),
    #     ('r10', 'R10'),
    #     ('r11', 'R11'),
    #     ('polvo', 'Polvo'),
    #     ('liquido', 'Liquido'),
    #     ('satinado', 'Satinado'),
    #     ('cepillado_mate', 'Cepillado / Mate'),
    #     ('cepillado_brillado', 'Cepillado / Brillado'),
    #     ('rockface', 'Rockface'),
    #     ('bamboo_alt', 'Bamboo'),
    #     ('moonface', 'Moonface'),
    #     ('corte_disco', 'Corte Disco'),
    #     ('guillotina', 'Guillotina'),
    #     ('mate_destapado', 'Mate Destapado'),
    #     ('mate_retapado', 'Mate Retapado'),
    #     ('sandblasteado_retapado', 'Sandblasteado Retapado'),
    #     ('pulido_brillado_retapado', 'Pulido Brillado Retapado'),
    #     ('cepillado_retapado', 'Cepillado Retapado'),
    #     ('riverwashed', 'Riverwashed'),
    #     ('slate', 'Slate'),
    # ], string='Acabado', help='Tipo de acabado del producto')
    
    x_bloque = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen'
    )
    
    x_formato = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto')
    
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

## ./models/stock_lot_hold.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta

class StockLotHold(models.Model):
    _name = 'stock.lot.hold'
    _description = 'Hold/Reserva Manual de Lotes'
    _order = 'create_date desc'
    _rec_name = 'lot_id'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    quant_id = fields.Many2one(
        'stock.quant',
        string='Quant',
        required=True,
        ondelete='cascade',
        index=True,
        help='Referencia al quant específico que se está reservando'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Reservado Para',
        required=True,
        help='Cliente o contacto para quien se reserva el lote'
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Reservado Por',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        help='Usuario que creó la reserva'
    )
    
    fecha_inicio = fields.Datetime(
        string='Fecha de Reserva',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
        help='Fecha y hora en que se creó la reserva'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Fecha de Expiración',
        compute='_compute_fecha_expiracion',
        store=True,
        help='Fecha en que expira la reserva (10 días desde inicio)'
    )
    
    estado = fields.Selection([
        ('activo', 'Activo'),
        ('expirado', 'Expirado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='activo', required=True, index=True)
    
    notas = fields.Text(
        string='Notas',
        help='Notas adicionales sobre esta reserva'
    )
    
    dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_dias_restantes',
        store=False,  # CAMBIADO: No se guarda en BD
        help='Días restantes hasta la expiración'
    )
    
    esta_expirado = fields.Boolean(
        string='Expirado',
        compute='_compute_esta_expirado',  # CAMBIADO: Método separado
        store=True,
        help='Indica si la reserva ya expiró'
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

    @api.depends('fecha_inicio')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración (10 días desde inicio)"""
        for record in self:
            if record.fecha_inicio:
                record.fecha_expiracion = record.fecha_inicio + timedelta(days=10)
            else:
                record.fecha_expiracion = fields.Datetime.now() + timedelta(days=10)

    @api.depends('fecha_expiracion')
    def _compute_dias_restantes(self):
        """Calcular días restantes hasta expiración"""
        now = fields.Datetime.now()
        for record in self:
            if record.fecha_expiracion:
                delta = record.fecha_expiracion - now
                record.dias_restantes = delta.days
            else:
                record.dias_restantes = 0

    @api.depends('fecha_expiracion', 'estado')
    def _compute_esta_expirado(self):
        """Marcar si la reserva está expirada"""
        now = fields.Datetime.now()
        for record in self:
            if record.fecha_expiracion and record.estado == 'activo':
                delta = record.fecha_expiracion - now
                record.esta_expirado = delta.days < 0
            else:
                record.esta_expirado = False

    @api.model
    def _cron_expire_holds(self):
        """Cron job para expirar reservas automáticamente"""
        now = fields.Datetime.now()
        holds_expirados = self.search([
            ('estado', '=', 'activo'),
            ('fecha_expiracion', '<=', now)
        ])
        
        if holds_expirados:
            holds_expirados.write({'estado': 'expirado'})
            # Forzar recálculo de estados en los quants relacionados
            quants = holds_expirados.mapped('quant_id')
            quants._compute_estado_hold()
            
        return True

    def action_cancelar_hold(self):
        """Cancelar manualmente una reserva"""
        self.ensure_one()
        self.write({'estado': 'cancelado'})
        # Forzar recálculo del estado del quant
        self.quant_id._compute_estado_hold()
        return True

    def action_renovar_hold(self):
        """Renovar la reserva por 10 días más"""
        self.ensure_one()
        if self.estado == 'activo':
            self.write({
                'fecha_inicio': fields.Datetime.now(),
                'estado': 'activo'
            })
            # Forzar recálculo de fecha de expiración
            self._compute_fecha_expiracion()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '¡Éxito!',
                    'message': f'Reserva renovada hasta {self.fecha_expiracion.strftime("%d/%m/%Y")}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, verificar que no haya otro hold activo en el mismo quant"""
        for vals in vals_list:
            if 'quant_id' in vals:
                hold_existente = self.search([
                    ('quant_id', '=', vals['quant_id']),
                    ('estado', '=', 'activo')
                ], limit=1)
                if hold_existente:
                    raise models.ValidationError(
                        f"Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} "
                        f"que expira el {hold_existente.fecha_expiracion.strftime('%d/%m/%Y')}"
                    )
        return super().create(vals_list)

    def unlink(self):
        """Al eliminar, forzar recálculo de estados"""
        quants = self.mapped('quant_id')
        result = super().unlink()
        quants._compute_estado_hold()
        return result

    def write(self, vals):
        """Al modificar estado, forzar recálculo"""
        result = super().write(vals)
        if 'estado' in vals:
            self.mapped('quant_id')._compute_estado_hold()
        return result```

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
    
    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)'
    )
    
    x_formato_temp = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto (se guardará en el lote)')
    
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
    
    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False
    )
    
    x_formato_lote = fields.Selection(
        related='lot_id.x_formato',
        string='Formato Lote',
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

    @api.onchange('product_id', 'location_id')
    def _onchange_product_location_filter_lots(self):
        """
        Filtrar el dominio de lotes disponibles basado en:
        1. Lotes sin hold (disponibles para todos)
        2. Lotes con hold para el cliente de este picking
        
        Esto hace que en el campo lot_id solo aparezcan lotes válidos.
        Solo aplica en pickings de salida (entregas).
        
        IMPORTANTE: Este es solo un filtro VISUAL para ayudar al usuario.
        NO es una validación - el usuario técnicamente podría seleccionar otro lote,
        pero el sistema automático no asignará lotes con hold gracias al método
        _get_available_quantity en stock_quant.py
        """
        if not self.product_id or not self.picking_id:
            return {}
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if self.picking_id.picking_type_code != 'outgoing':
            return {}
        
        # Obtener el cliente del picking
        cliente_picking = self.picking_id.partner_id
        if self.move_id and self.move_id.sale_line_id:
            cliente_picking = self.move_id.sale_line_id.order_id.partner_id
        
        if not cliente_picking:
            return {}
        
        # Buscar todos los quants del producto en la ubicación
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('quantity', '>', 0),
        ])
        
        # Filtrar lotes válidos:
        # 1. Lotes SIN hold (disponibles para todos)
        # 2. Lotes CON hold pero para ESTE cliente
        lotes_validos = []
        
        for quant in quants:
            if quant.lot_id:
                # Si no tiene hold, está disponible
                if not quant.x_tiene_hold:
                    lotes_validos.append(quant.lot_id.id)
                # Si tiene hold pero es para este cliente, está disponible
                elif quant.x_hold_activo_id and quant.x_hold_activo_id.partner_id == cliente_picking:
                    lotes_validos.append(quant.lot_id.id)
                # Si tiene hold para otro cliente, NO aparece en la lista
        
        # Retornar dominio que filtra los lotes
        if lotes_validos:
            return {
                'domain': {
                    'lot_id': [
                        ('id', 'in', lotes_validos),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
        else:
            # Si no hay lotes válidos, mostrar dominio vacío
            return {
                'domain': {
                    'lot_id': [('id', '=', False)]
                }
            }

    # ✅ ELIMINADO: @api.constrains('lot_id', 'quantity', 'picking_id')
    # Ya NO validamos aquí porque causaba el error al confirmar la orden
    # La restricción real está en stock_quant._get_available_quantity()
    # que previene la asignación automática de lotes con hold

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """
        Cargar dimensiones del lote si ya existen y calcular cantidad.
        
        COMPORTAMIENTO:
        - En RECEPCIONES (incoming): Calcula qty_done = alto × ancho del lote
        - En ENTREGAS (outgoing): Busca la cantidad disponible del lote en inventario
        """
        if self.lot_id:
            # Cargar valores en campos temporales
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
            self.x_bloque_temp = self.lot_id.x_bloque
            self.x_formato_temp = self.lot_id.x_formato
            
            # ============================================================================
            # CORRECCIÓN DEL BUG: Ahora manejamos TANTO recepciones como entregas
            # ============================================================================
            if self.picking_id:
                if self.picking_id.picking_type_code == 'incoming':
                    # RECEPCIÓN: Calcular por dimensiones (como antes)
                    if self.lot_id.x_alto and self.lot_id.x_ancho:
                        self.qty_done = self.lot_id.x_alto * self.lot_id.x_ancho
                
                elif self.picking_id.picking_type_code == 'outgoing':
                    # ENTREGA: Buscar cantidad disponible del lote en la ubicación de origen
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', self.lot_id.id),
                        ('location_id', '=', self.location_id.id),
                        ('product_id', '=', self.product_id.id)
                    ], limit=1)
                    
                    if quant:
                        # Usar la cantidad disponible del quant
                        # available_quantity ya considera las reservas y holds
                        cantidad_disponible = quant.available_quantity
                        
                        # Si hay cantidad disponible, asignarla
                        if cantidad_disponible > 0:
                            # Limitar al máximo de product_uom_qty del move
                            if self.move_id and self.move_id.product_uom_qty:
                                self.qty_done = min(cantidad_disponible, self.move_id.product_uom_qty)
                            else:
                                self.qty_done = cantidad_disponible
                        else:
                            # Si no hay cantidad disponible, dejar en 0
                            self.qty_done = 0.0
                    else:
                        # Si no existe el quant, poner en 0
                        self.qty_done = 0.0
            # ============================================================================

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular automáticamente qty_done (m²) cuando se ingresan alto y ancho
        Solo aplica en recepciones"""
        if self.picking_id and self.picking_id.picking_type_code == 'incoming':
            if self.x_alto_temp and self.x_ancho_temp:
                self.qty_done = self.x_alto_temp * self.x_ancho_temp

    def write(self, vals):
        """Guardar dimensiones en el lote al confirmar (solo en recepciones)"""
        # Primero ejecutar el write original
        result = super().write(vals)
        
        # Después del write, verificar si hay dimensiones que guardar en el lote
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp', 'x_bloque_temp', 'x_formato_temp']
        has_dimensions = any(field in vals for field in dimension_fields)
        
        # Si se modificó el lote_id o hay dimensiones, actualizar el lote
        # SOLO en operaciones de entrada (recepciones)
        if 'lot_id' in vals or has_dimensions:
            for line in self:
                if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    lot_vals = {}
                    
                    # Usar los valores actuales de la línea (ya actualizados por el super().write())
                    if line.x_grosor_temp:
                        lot_vals['x_grosor'] = line.x_grosor_temp
                    if line.x_alto_temp:
                        lot_vals['x_alto'] = line.x_alto_temp
                    if line.x_ancho_temp:
                        lot_vals['x_ancho'] = line.x_ancho_temp
                    if line.x_bloque_temp:
                        lot_vals['x_bloque'] = line.x_bloque_temp
                    if line.x_formato_temp:
                        lot_vals['x_formato'] = line.x_formato_temp
                    
                    # Solo actualizar si hay valores que guardar
                    if lot_vals:
                        line.lot_id.write(lot_vals)
        
        # Calcular qty_done si se modifican alto o ancho (evitar recursión)
        # Solo en recepciones
        if ('x_alto_temp' in vals or 'x_ancho_temp' in vals) and 'qty_done' not in vals:
            for line in self:
                if line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    alto = line.x_alto_temp
                    ancho = line.x_ancho_temp
                    if alto and ancho:
                        # Usar super() para evitar recursión infinita
                        super(StockMoveLine, line).write({'qty_done': alto * ancho})
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear (solo en recepciones)"""
        # Calcular cantidad automáticamente si hay alto y ancho (solo en recepciones)
        for vals in vals_list:
            # Verificar si es una recepción antes de calcular
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    if vals.get('x_alto_temp') and vals.get('x_ancho_temp'):
                        # Sobrescribir qty_done con el cálculo de m²
                        vals['qty_done'] = vals['x_alto_temp'] * vals['x_ancho_temp']
        
        lines = super().create(vals_list)
        
        # Guardar dimensiones en el lote después de crear la línea
        # SOLO en operaciones de entrada (recepciones)
        for line, vals in zip(lines, vals_list):
            if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                lot_vals = {}
                
                # Usar los valores de la línea recién creada
                if line.x_grosor_temp:
                    lot_vals['x_grosor'] = line.x_grosor_temp
                if line.x_alto_temp:
                    lot_vals['x_alto'] = line.x_alto_temp
                if line.x_ancho_temp:
                    lot_vals['x_ancho'] = line.x_ancho_temp
                if line.x_bloque_temp:
                    lot_vals['x_bloque'] = line.x_bloque_temp
                if line.x_formato_temp:
                    lot_vals['x_formato'] = line.x_formato_temp
                
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
        }```

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
                # Pasar el cliente permitido en el contexto
                self = self.with_context(allowed_partner_id=picking.partner_id.id)
        
        result = super(StockPicking, self).action_assign()
        _logger.info("🟢 [STOCK PICKING] action_assign() completado")
        return result
    
    def _action_assign(self):
        """
        Override para limpiar lotes automáticos después de la asignación
        Este método se ejecuta cuando Odoo asigna/reserva inventario automáticamente
        """
        _logger.info("="*80)
        _logger.info("🟡 [STOCK PICKING] _action_assign() INICIANDO para picking(s): %s", self.mapped('name'))
        
        # Ejecutar el proceso normal de asignación (esto crea los lotes automáticamente)
        res = super(StockPicking, self)._action_assign()
        _logger.info("🟡 [STOCK PICKING] Super _action_assign() completado")
        
        # Después de la asignación, limpiar TODOS los lotes que se asignaron automáticamente
        for picking in self:
            _logger.info("🟡 [STOCK PICKING] Procesando picking: %s (ID: %s)", picking.name, picking.id)
            _logger.info("🟡 [STOCK PICKING] Sale Order: %s", picking.sale_id.name if picking.sale_id else 'No tiene sale_id')
            _logger.info("🟡 [STOCK PICKING] Picking Type: %s", picking.picking_type_code)
            
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
                        
                        # Forzar commit para asegurar que se guardan los cambios
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
                for move_line in picking.move_line_ids:
                    if move_line.lot_id:
                        _logger.info("🔴 [STOCK PICKING] Verificando lote: %s para move_line: %s", 
                                    move_line.lot_id.name, move_line.id)
                        
                        # Verificar si el lote tiene hold
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', move_line.lot_id.id),
                            ('location_id', '=', move_line.location_id.id),
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

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Campos relacionados del lote
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    # x_acabado = fields.Selection(related='lot_id.x_acabado', string='Acabado', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_formato = fields.Selection(related='lot_id.x_formato', string='Formato', readonly=True)
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
    
    # NUEVOS CAMPOS PARA HOLD MANUAL
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=True,
        help='Indica si el lote tiene una reserva manual activa'
    )
    
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
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
        help='Días restantes del hold'
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
                estados.append({
                    'type': 'hold',
                    'icon': '🔒',
                    'label': f'HOLD para {quant.x_hold_para}',
                    'detail': f'Expira en {quant.x_hold_dias_restantes} días',
                    'class': 'text-warning' if quant.x_hold_dias_restantes <= 3 else 'text-info'
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

    # NUEVAS ACCIONES PARA HOLD
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        # Verificar si ya tiene hold activo
        if self.x_tiene_hold:
            raise models.UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {self.x_hold_dias_restantes} días.'
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

    def _get_available_quantity(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
        """
        ✅ CORRECCIÓN COMPLETA del método _get_available_quantity
        
        Este método se llama sobre un RECORDSET de múltiples quants,
        NO sobre un solo quant, por lo que NO podemos usar self.x_tiene_hold directamente.
        
        El método debe:
        1. Llamar al padre para obtener la cantidad disponible base
        2. Filtrar los quants con hold que NO son para el cliente actual
        3. Restar esas cantidades del total disponible
        """
        # Llamar al método padre para obtener la cantidad base disponible
        available_qty = super(StockQuant, self)._get_available_quantity(
            product_id, location_id, lot_id, package_id, owner_id, strict, allow_negative
        )
        
        # Si no hay cantidad disponible, retornar inmediatamente
        if available_qty <= 0:
            return available_qty
        
        # Obtener el cliente permitido del contexto (si existe)
        cliente_permitido_id = self._context.get('allowed_partner_id')
        
        # Iterar sobre los quants de este recordset y restar cantidades bloqueadas por holds
        cantidad_bloqueada = 0.0
        
        for quant in self:
            # Verificar si este quant tiene un hold activo
            if quant.x_tiene_hold and quant.x_hold_activo_id:
                # Si hay un cliente permitido y es el mismo del hold, este quant NO está bloqueado
                if cliente_permitido_id and quant.x_hold_activo_id.partner_id.id == cliente_permitido_id:
                    continue  # Este quant está disponible para este cliente
                
                # Si no hay cliente permitido o es diferente, bloquear este quant
                cantidad_bloqueada += quant.quantity
        
        # Retornar la cantidad disponible menos la cantidad bloqueada por holds
        return max(0.0, available_qty - cantidad_bloqueada)```

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

## ./views/stock_lot_hold_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista Form del Wizard de Hold -->
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
                        <field name="x_formato" readonly="1"/>
                        <field name="x_grosor" readonly="1"/>
                        <field name="x_alto" readonly="1"/>
                        <field name="x_ancho" readonly="1"/>
                        <field name="x_bloque" readonly="1"/>
                    </group>
                </group>
                
                <group>
                    <group string="Reserva">
                        <field name="partner_id" 
                               placeholder="Seleccione el cliente..."
                               options="{'no_create': True}"/>
                        <field name="fecha_expiracion" readonly="1"/>
                    </group>
                    
                    <group string="Notas">
                        <field name="notas" 
                               nolabel="1" 
                               placeholder="Ej: Para proyecto X, Cotización Y, etc."/>
                    </group>
                </group>
                
                <div class="alert alert-info" role="alert">
                    <strong>Nota:</strong> La reserva expirará automáticamente en 10 días. 
                    Puede renovarla desde la vista de reservas si es necesario.
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
                
                <!-- Campos ocultos necesarios -->
                <field name="quant_id" invisible="1"/>
            </form>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_hold_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista Form del Wizard de Hold -->
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
                        <field name="x_formato" readonly="1"/>
                        <field name="x_grosor" readonly="1"/>
                        <field name="x_alto" readonly="1"/>
                        <field name="x_ancho" readonly="1"/>
                        <field name="x_bloque" readonly="1"/>
                    </group>
                </group>
                
                <group>
                    <group string="Reserva">
                        <field name="partner_id" 
                               placeholder="Seleccione el cliente..."
                               options="{'no_create': True}"/>
                        <field name="fecha_expiracion" readonly="1"/>
                    </group>
                    
                    <group string="Notas">
                        <field name="notas" 
                               nolabel="1" 
                               placeholder="Ej: Para proyecto X, Cotización Y, etc."/>
                    </group>
                </group>
                
                <div class="alert alert-info" role="alert">
                    <strong>Nota:</strong> La reserva expirará automáticamente en 10 días. 
                    Puede renovarla desde la vista de reservas si es necesario.
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
                
                <!-- Campos ocultos necesarios -->
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
                                <!-- <field name="x_acabado" 
                                       placeholder="Selecciona un acabado..."/> -->
                                <field name="x_formato" 
                                       placeholder="Selecciona un formato..."/>
                                <field name="x_bloque" 
                                       placeholder="Identificación del bloque"/>
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
                <!-- <field name="x_acabado" optional="show" string="Acabado"/> -->
                <field name="x_bloque" optional="show" string="Bloque"/>
                <field name="x_formato" optional="show" string="Formato"/>
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
                <!-- <field name="x_acabado_temp" 
                       optional="show" 
                       string="Acabado"
                       readonly="not x_is_incoming"/> -->
                <field name="x_bloque_temp" 
                       optional="show" 
                       string="Bloque"
                       readonly="not x_is_incoming"/>
                <field name="x_formato_temp" 
                       optional="show" 
                       string="Formato"
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
                <!-- <field name="x_acabado_lote" optional="show" string="Acabado"/> -->
                <field name="x_bloque_lote" optional="show" string="Bloque"/>
                <field name="x_formato_lote" optional="show" string="Formato"/>
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
                    <!-- <field name="x_acabado_temp" 
                           string="Acabado"
                           readonly="not x_is_incoming"/> -->
                    <field name="x_bloque_temp" 
                           string="Bloque"
                           readonly="not x_is_incoming"/>
                    <field name="x_formato_temp" 
                           string="Formato"
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
                <field name="x_formato" optional="show" string="Formato"/>
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
                <field name="x_formato" optional="show" string="Formato" readonly="1"/>
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
# -*- coding: utf-8 -*-
from odoo import models, fields, api
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
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Reservar Para',
        required=True,
        help='Cliente o contacto para quien se reserva el lote'
    )
    
    fecha_expiracion = fields.Datetime(
        string='Expira el',
        compute='_compute_fecha_expiracion',
        readonly=True,
        help='Fecha de expiración (10 días desde hoy)'
    )
    
    notas = fields.Text(
        string='Notas',
        placeholder='Notas adicionales sobre esta reserva...'
    )
    
    # Campos informativos del lote
    x_grosor = fields.Float(related='lot_id.x_grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', readonly=True)
    x_formato = fields.Selection(related='lot_id.x_formato', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', readonly=True)

    @api.depends('create_date')
    def _compute_fecha_expiracion(self):
        """Calcular fecha de expiración (10 días)"""
        for record in self:
            record.fecha_expiracion = fields.Datetime.now() + timedelta(days=10)

    def action_crear_hold(self):
        """Crear el hold y cerrar el wizard"""
        self.ensure_one()
        
        # Verificar que no haya hold activo
        hold_existente = self.env['stock.lot.hold'].search([
            ('quant_id', '=', self.quant_id.id),
            ('estado', '=', 'activo')
        ], limit=1)
        
        if hold_existente:
            raise models.UserError(
                f'Este lote ya tiene una reserva activa para {hold_existente.partner_id.name} '
                f'que expira el {hold_existente.fecha_expiracion.strftime("%d/%m/%Y")}'
            )
        
        # Crear el hold
        hold = self.env['stock.lot.hold'].create({
            'lot_id': self.lot_id.id,
            'quant_id': self.quant_id.id,
            'partner_id': self.partner_id.id,
            'notas': self.notas,
        })
        
        # Retornar notificación de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Reserva Creada!',
                'message': f'Lote {self.lot_id.name} reservado para {self.partner_id.name} hasta el {hold.fecha_expiracion.strftime("%d/%m/%Y %H:%M")}',
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


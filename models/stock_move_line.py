# -*- coding: utf-8 -*-
# models/stock_move_line.py
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .utils.lot_dimension_sync import LotDimensionSync
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
# ✅ IMPORTACIÓN AGREGADA AQUÍ ABAJO
from .utils.hold_validator import HoldValidator 
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    # ==================== CAMPOS TEMPORALES DE DIMENSIONES ====================
    x_color_temp = fields.Char(
        string='Color',
        help='Color del producto (se guardará en el lote)'
    )

    x_grosor_temp = fields.Char(
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
    
    x_tipo_temp = fields.Selection(
        [('placa', 'Placa'), ('formato', 'Formato'), ('pieza', 'Pieza')],
        string='Tipo',
        help='Tipo de producto (se guardará en el lote)'
    )
    
    x_numero_placa_temp = fields.Integer(
        string='No. Placa',
        help='Número de placa (se guardará en el lote)'
    )
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
    x_proveedor_temp = fields.Char(string='Proveedor')
    x_origen_temp = fields.Char(string='Origen')
    # ==================== CAMPOS COMPUTADOS ====================
    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False
    )
    
    # ==================== CAMPOS RELATED DEL LOTE ====================
    x_color_lote = fields.Char(
        related='lot_id.x_color',
        string='Color Lote',
        readonly=True,
        store=False
    )

    x_grosor_lote = fields.Char(
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
    
    x_numero_placa_lote = fields.Integer(
        related='lot_id.x_numero_placa',
        string='No. Placa Lote',
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

    x_proveedor_lote = fields.Char(related='lot_id.x_proveedor', string='Proveedor Lote', readonly=True)
    x_origen_lote = fields.Char(related='lot_id.x_origen', string='Origen Lote', readonly=True)
    
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
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción"""
        for line in self:
            line.x_is_incoming = (
                line.picking_id and 
                line.picking_id.picking_type_code == 'incoming'
            )
    
    # ==================== VALIDACIONES DE HOLDS ====================
    @api.constrains('lot_id', 'picking_id', 'state')
    def _check_lot_hold(self):
        """Validación de holds al asignar/confirmar lotes con soporte multi-compañía"""
        # Bypass si ya se validó - CORREGIDO PARA ODOO 19
        if self.env.context.get('skip_hold_validation'):
            return
        
        validator = HoldValidator(self.env)
        
        for line in self:
            # Solo validar pickings de salida con lote asignado
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'outgoing':
                continue
            
            # Obtener cliente
            partner = validator.get_customer_from_picking(line)
            if not partner:
                continue
            
            # Obtener compañía del picking
            company_id = line.picking_id.company_id.id if line.picking_id.company_id else self.env.company.id
            
            # Validar hold considerando compañía
            try:
                validator.validate_lot_assignment(
                    line.lot_id.id,
                    line.location_id.id,
                    partner.id,
                    company_id
                )
            except ValidationError:
                raise
    
    # ==================== ONCHANGE - FILTRADO DE LOTES ====================
    @api.onchange('product_id', 'location_id', 'picking_id')
    def _onchange_product_location_filter_lots(self):
        """Filtrar lotes disponibles según holds del cliente y compañía"""
        if not self.product_id or not self.picking_id:
            return {}
        
        # Solo aplicar en pickings de salida
        if self.picking_id.picking_type_code != 'outgoing':
            return {}
        
        validator = HoldValidator(self.env)
        partner = validator.get_customer_from_picking(self)
        
        if not partner or not self.location_id:
            return {'domain': {'lot_id': [('id', '=', False)]}}
        
        # Obtener compañía del picking
        company_id = self.picking_id.company_id.id if self.picking_id.company_id else self.env.company.id
        
        # Obtener lotes disponibles considerando compañía
        available_lots = validator.get_available_lots(
            self.product_id.id,
            self.location_id.id,
            partner.id,
            company_id
        )
        
        if available_lots:
            return {
                'domain': {
                    'lot_id': [
                        ('id', 'in', available_lots),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
        else:
            return {'domain': {'lot_id': [('id', '=', False)]}}
    
    # ==================== ONCHANGE - DIMENSIONES ====================
    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote y calcular cantidad"""
        if not self.lot_id:
            return
        
        # Cargar dimensiones
        LotDimensionSync.load_dimensions_from_lot(self)
        
        if not self.picking_id:
            return
        
        # Calcular cantidad según tipo de picking
        if self.picking_id.picking_type_code == 'incoming':
            # Recepción: Calcular por dimensiones
            self.qty_done = LotDimensionSync.calculate_area(
                self.lot_id.x_alto,
                self.lot_id.x_ancho
            )
        
        elif self.picking_id.picking_type_code == 'outgoing':
            # Entrega: Usar cantidad disponible
            move_qty = self.move_id.product_uom_qty if self.move_id else None
            
            self.qty_done = LotDimensionSync.get_available_quantity(
                self.env,
                self.lot_id.id,
                self.location_id.id,
                self.product_id.id,
                move_qty
            )
    
    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular qty_done automáticamente cuando se ingresan dimensiones"""
        if not self.picking_id or self.picking_id.picking_type_code != 'incoming':
            return
        
        self.qty_done = LotDimensionSync.calculate_area(
            self.x_alto_temp,
            self.x_ancho_temp
        )
    
    # ==================== WRITE ====================
    def write(self, vals):
        """Guardar dimensiones en el lote y validar holds con soporte multi-compañía"""
        # Validar hold si se está cambiando el lote
        if 'lot_id' in vals and vals['lot_id']:
            self._validate_lot_hold_on_write(vals['lot_id'])
        
        # Ejecutar write original
        result = super().write(vals)
        
        # Sincronizar dimensiones al lote
        self._sync_dimensions_to_lot(vals)
        
        # Calcular cantidad si se modificaron dimensiones
        self._update_qty_done_if_needed(vals)
        
        return result
    
    def _validate_lot_hold_on_write(self, new_lot_id):
        """Valida hold al cambiar lote en write con soporte multi-compañía"""
        validator = HoldValidator(self.env)
        
        for line in self:
            # Solo validar pickings de salida
            if not line.picking_id or line.picking_id.picking_type_code != 'outgoing':
                continue
            
            partner = validator.get_customer_from_picking(line)
            if not partner:
                continue
            
            # Obtener compañía del picking
            company_id = line.picking_id.company_id.id if line.picking_id.company_id else self.env.company.id
            
            try:
                validator.validate_lot_assignment(
                    new_lot_id,
                    line.location_id.id,
                    partner.id,
                    company_id
                )
            except ValidationError:
                raise
    
    def _sync_dimensions_to_lot(self, vals):
        """Sincroniza dimensiones temporales al lote"""
        dimension_fields = list(LotDimensionSync.DIMENSION_MAPPING.keys())
        has_dimensions = any(field in vals for field in dimension_fields)
        
        if 'lot_id' not in vals and not has_dimensions:
            return
        
        for line in self:
            # Solo en recepciones
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'incoming':
                continue
            
            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)
            
            if lot_vals:
                line.lot_id.write(lot_vals)
    
    def _update_qty_done_if_needed(self, vals):
        """Actualiza qty_done si cambiaron dimensiones"""
        if ('x_alto_temp' not in vals and 'x_ancho_temp' not in vals) or 'qty_done' in vals:
            return
        
        for line in self:
            if not line.picking_id or line.picking_id.picking_type_code != 'incoming':
                continue
            
            qty_done = LotDimensionSync.calculate_area(
                line.x_alto_temp,
                line.x_ancho_temp
            )
            
            if qty_done > 0:
                super(StockMoveLine, line).write({'qty_done': qty_done})
    
    # ==================== CREATE ====================
    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear"""
        # Pre-calcular qty_done en recepciones
        for vals in vals_list:
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    qty_done = LotDimensionSync.calculate_area(
                        vals.get('x_alto_temp'),
                        vals.get('x_ancho_temp')
                    )
                    if qty_done > 0:
                        vals['qty_done'] = qty_done
        
        # Crear registros
        lines = super().create(vals_list)
        
        # Sincronizar dimensiones al lote
        for line in lines:
            if not line.lot_id or not line.picking_id:
                continue
            
            if line.picking_id.picking_type_code != 'incoming':
                continue
            
            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)
            if lot_vals:
                line.lot_id.write(lot_vals)
        
        return lines
    
    # ==================== ACCIONES ====================
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        
        if not self.lot_id:
            return NotificationBuilder.build_warning(
                'Advertencia',
                'Debe seleccionar un lote primero'
            )
        
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
            raise UserError('Debe seleccionar un lote primero.')
        
        return PhotoHelper.build_photo_gallery_action(
            self.lot_id.id,
            self.lot_id.name
        )
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    x_grosor = fields.Float(
        related='lot_id.x_grosor',
        string='Grosor (cm)',
        readonly=True,
        store=False
    )
    
    x_alto = fields.Float(
        related='lot_id.x_alto',
        string='Alto (m)',
        readonly=True,
        store=False
    )
    
    x_ancho = fields.Float(
        related='lot_id.x_ancho',
        string='Ancho (m)',
        readonly=True,
        store=False
    )
    
    # x_acabado = fields.Selection(
    #     related='lot_id.x_acabado',
    #     string='Acabado',
    #     readonly=True,
    #     store=False
    # )
    
    x_bloque = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque',
        readonly=True,
        store=False
    )
    
    x_formato = fields.Selection(
        related='lot_id.x_formato',
        string='Formato',
        readonly=True,
        store=False
    )
    
    x_fotografia_principal = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto',
        readonly=True,
        store=False
    )
    
    x_cantidad_fotos = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos',
        readonly=True,
        store=False
    )
    
    # ========== NUEVOS CAMPOS PARA ESTADOS ==========
    
    x_esta_reservado = fields.Boolean(
        string='Está Reservado',
        compute='_compute_estados_placa',
        store=False,
        help='Indica si el lote está reservado'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estados_placa',
        store=False,
        help='Indica si el lote está en una orden de entrega'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=False,
        help='Indica si el lote tiene detalles especiales'
    )
    
    x_detalles_placa = fields.Text(
        related='lot_id.x_detalles_placa',
        string='Detalles de la Placa',
        readonly=True,
        store=False
    )
    
    estado_placa = fields.Char(
        string='Estado',
        compute='_compute_estado_placa',
        store=False
    )
    
    # ========== MÉTODOS COMPUTE ==========
    
    @api.depends('lot_id', 'reserved_quantity')
    def _compute_estados_placa(self):
        """Calcular si está reservado o en orden de entrega"""
        for quant in self:
            # Verificar si está reservado (tiene cantidad reservada)
            quant.x_esta_reservado = quant.reserved_quantity > 0
            
            # Verificar si está en una orden de entrega (picking en proceso)
            if quant.lot_id:
                en_orden = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                    ('picking_id.state', 'in', ['assigned', 'confirmed', 'waiting'])
                ], limit=1)
                quant.x_en_orden_entrega = bool(en_orden)
            else:
                quant.x_en_orden_entrega = False
    
    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si el lote tiene detalles"""
        for quant in self:
            quant.x_tiene_detalles = bool(quant.lot_id and quant.lot_id.x_detalles_placa)
    
    @api.depends('x_esta_reservado', 'x_en_orden_entrega', 'x_tiene_detalles')
    def _compute_estado_placa(self):
        """Campo dummy para el widget de iconos"""
        for quant in self:
            quant.estado_placa = 'status'
    
    # ========== MÉTODOS DE ACCIÓN ==========
    
    def action_view_lot_photos(self):
        """Ver y gestionar fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'No hay lote asociado a esta ubicación',
                    'type': 'warning',
                }
            }
        
        return {
            'name': f'Fotografías - {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            }
        }
    
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote desde ubicaciones"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'No hay lote asociado a esta ubicación',
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
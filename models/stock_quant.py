# -*- coding: utf-8 -*-
from odoo import models, fields

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
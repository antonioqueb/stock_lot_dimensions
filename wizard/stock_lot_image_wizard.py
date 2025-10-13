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
        }
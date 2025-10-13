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

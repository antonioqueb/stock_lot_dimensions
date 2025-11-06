# -*- coding: utf-8 -*-
# models/stock_lot_image.py
from odoo import models, fields, api
from .utils.image_processor import ImageProcessor
from .utils.metadata_fields import MetadataFields


class StockLotImage(models.Model):
    _name = 'stock.lot.image'
    _description = 'Fotografías de Lotes'
    _order = ImageProcessor.get_default_order()
    
    # ==================== CAMPOS METADATA ====================
    name = MetadataFields.get_name_field(default_name='Fotografía')
    sequence = MetadataFields.get_sequence_field(default=10)
    notas = MetadataFields.get_notes_field()
    fecha_captura = MetadataFields.get_capture_date_field()
    
    # ==================== CAMPOS DE RELACIÓN ====================
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # ==================== CAMPOS DE IMAGEN ====================
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
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('image')
    def _compute_image_small(self):
        """Generar miniatura de la imagen"""
        ImageProcessor.compute_thumbnail(self)
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
    )
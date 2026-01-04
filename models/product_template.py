# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_color = fields.Char(
        string='Color Estándar',
        help='Color base definido para este producto'
    )
    x_grosor = fields.Float(
        string='Grosor Nominal (cm)',
        digits=(10, 2),
        help='Grosor estándar definido para este producto'
    )
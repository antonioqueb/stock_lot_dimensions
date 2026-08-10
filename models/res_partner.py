# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    x_es_arquitecto = fields.Boolean(
        string='Es Embajador',
        default=False,
        help='Indica si este contacto es un embajador'
    )
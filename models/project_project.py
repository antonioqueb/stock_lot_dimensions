# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectProject(models.Model):
    _inherit = 'project.project'
    
    x_es_proyecto_marmol = fields.Boolean(
        string='Es Proyecto de Mármol',
        default=False,
        help='Indica si este proyecto está relacionado con reservas de lotes de mármol'
    )
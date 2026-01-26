# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_color = fields.Char(
        string='Color Estándar',
        help='Color base definido para este producto'
    )
    x_grosor = fields.Char(
        string='Grosor Nominal (cm)',
        digits=(10, 2),
        help='Grosor estándar definido para este producto'
    )

    x_acabado = fields.Char(
        string='Acabado Superficial',
        help='Tipo de acabado superficial del producto'
    )

    x_marca = fields.Char(
        string='Marca Comercial',
        help='Marca comercial asociada al producto'
    )

    x_acabado_producto = fields.Char(
        string='Tipo de Producto',
        help='Categoría o tipo específico del producto'
    )

    x_uso_recomendado = fields.Char(
        string='Uso Recomendado',
        help='Uso sugerido para este producto'
    )

    x_dureza = fields.Char(
        string='Dureza (Shore A)',
        help='Valor de dureza del material según la escala Shore A'
    )

    x_calidad_material = fields.Char(
        string='Calidad del Material',
        help='Descripción de la calidad del material del producto'
    )

    x_nombre_generico = fields.Char(
        string='Nombre Genérico',
        help='Nombre genérico del producto para identificación'
    )

    x_dimensiones = fields.Char(
        string='Dimensiones (LxAnxAl)',
        help='Dimensiones estándar del producto en Largo x Ancho x Alto'
    )






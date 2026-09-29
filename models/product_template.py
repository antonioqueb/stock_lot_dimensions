# -*- coding: utf-8 -*-
from odoo import api, models, fields

# La unidad del producto es texto libre, pero TODO el sistema la lee como
# Placa / Formato / Pieza (PL, worksheet, portal, x_tipo del lote). Una
# captura como 'PIEZAS' o 'PZ' tumbaba el Procesar PL con "Wrong value for
# stock.lot.x_tipo" (C177, BLOQUE TRAVERTINO VERACRUZ RUSTICO 80X80X80).
SOM_UNIT_ALIASES = {
    'placa': 'Placa', 'placas': 'Placa',
    'formato': 'Formato', 'formatos': 'Formato',
    'pieza': 'Pieza', 'piezas': 'Pieza', 'pz': 'Pieza', 'pzs': 'Pieza',
    'pza': 'Pieza', 'pzas': 'Pieza',
    'servicio': 'Servicio', 'servicios': 'Servicio',
}


def som_normalize_unit(value):
    if not value:
        return value
    raw = str(value).strip()
    return SOM_UNIT_ALIASES.get(raw.lower().rstrip('.'), raw)


class ProductTemplate(models.Model):
    _inherit = 'product.template'


    x_nombre_alternativo = fields.Char(
        string='Nombre Alternativo',
        help='Nombre alternativo o comercial del producto'
    )

    x_color = fields.Char(
        string='Color Estándar',
        help='Color base definido para este producto'
    )
    x_grosor = fields.Char(
        string='Grosor Nominal (cm)',
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

    x_unidad_del_producto = fields.Char(
        string='Unidad del Producto',
        help='Unidad de medida utilizada para este producto'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('x_unidad_del_producto'):
                vals['x_unidad_del_producto'] = som_normalize_unit(
                    vals['x_unidad_del_producto'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('x_unidad_del_producto'):
            vals = dict(vals, x_unidad_del_producto=som_normalize_unit(
                vals['x_unidad_del_producto']))
        return super().write(vals)






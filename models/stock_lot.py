# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockLot(models.Model):
    _inherit = 'stock.lot'

    x_grosor = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros'
    )
    
    x_alto = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros'
    )
    
    x_ancho = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros'
    )
    
    # x_acabado = fields.Selection([
    #     ('pulido', 'Pulido'),
    #     ('mate', 'Mate'),
    #     ('busardeado', 'Busardeado'),
    #     ('sandblasteado', 'Sandblasteado'),
    #     ('acido_ligero', 'Acido Ligero'),
    #     ('acido_rugoso', 'Acido Rugoso'),
    #     ('cepillado', 'Cepillado'),
    #     ('busardeado_cepillado', 'Busardeado + Cepillado'),
    #     ('sandblasteado_cepillado', 'Sandblasteado + Cepillado'),
    #     ('macheteado', 'Macheteado'),
    #     ('century', 'Century'),
    #     ('apomazado', 'Apomazado'),
    #     ('routeado_nivel1', 'Routeado Nivel 1 (2cm)'),
    #     ('routeado_nivel2', 'Routeado Nivel 2 (4cm)'),
    #     ('routeado_nivel3', 'Routeado Nivel 3 (6cm)'),
    #     ('flameado', 'Flameado'),
    #     ('al_corte', 'Al corte'),
    #     ('natural', 'Natural'),
    #     ('tomboleado', 'Tomboleado'),
    #     ('lino', 'Lino'),
    #     ('raw', 'Raw'),
    #     ('bamboo', 'Bamboo'),
    #     ('r10', 'R10'),
    #     ('r11', 'R11'),
    #     ('polvo', 'Polvo'),
    #     ('liquido', 'Liquido'),
    #     ('satinado', 'Satinado'),
    #     ('cepillado_mate', 'Cepillado / Mate'),
    #     ('cepillado_brillado', 'Cepillado / Brillado'),
    #     ('rockface', 'Rockface'),
    #     ('bamboo_alt', 'Bamboo'),
    #     ('moonface', 'Moonface'),
    #     ('corte_disco', 'Corte Disco'),
    #     ('guillotina', 'Guillotina'),
    #     ('mate_destapado', 'Mate Destapado'),
    #     ('mate_retapado', 'Mate Retapado'),
    #     ('sandblasteado_retapado', 'Sandblasteado Retapado'),
    #     ('pulido_brillado_retapado', 'Pulido Brillado Retapado'),
    #     ('cepillado_retapado', 'Cepillado Retapado'),
    #     ('riverwashed', 'Riverwashed'),
    #     ('slate', 'Slate'),
    # ], string='Acabado', help='Tipo de acabado del producto')
    
    x_bloque = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen'
    )

    x_atado = fields.Char(
        string='Atado',
        help='Identificación del atado'
    )
    
    x_formato = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto')
    
    x_fotografia_ids = fields.One2many(
        'stock.lot.image',
        'lot_id',
        string='Fotografías',
        help='Fotografías del producto/lote'
    )
    
    x_fotografia_principal = fields.Binary(
        string='Foto Principal',
        compute='_compute_fotografia_principal',
        store=False
    )
    
    x_tiene_fotografias = fields.Boolean(
        string='Tiene Fotos',
        compute='_compute_tiene_fotografias',
        store=True
    )
    
    x_cantidad_fotos = fields.Integer(
        string='# Fotos',
        compute='_compute_cantidad_fotos',
        store=True
    )
    
    x_detalles_placa = fields.Text(
        string='Detalles de la Placa',
        help='Detalles especiales: rota, barreno, release, etc.'
    )

    @api.depends('x_fotografia_ids')
    def _compute_fotografia_principal(self):
        """Obtener la primera fotografía como principal"""
        for record in self:
            if record.x_fotografia_ids:
                record.x_fotografia_principal = record.x_fotografia_ids[0].image
            else:
                record.x_fotografia_principal = False

    @api.depends('x_fotografia_ids')
    def _compute_tiene_fotografias(self):
        """Verificar si el lote tiene fotografías"""
        for record in self:
            record.x_tiene_fotografias = bool(record.x_fotografia_ids)

    @api.depends('x_fotografia_ids')
    def _compute_cantidad_fotos(self):
        """Contar número de fotografías"""
        for record in self:
            record.x_cantidad_fotos = len(record.x_fotografia_ids)

    def action_view_images(self):
        """Abrir vista de galería de imágenes del lote"""
        self.ensure_one()
        return {
            'name': f'Fotografías de {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,tree,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {
                'default_lot_id': self.id,
                'create': True,
            },
            'target': 'current',
        }
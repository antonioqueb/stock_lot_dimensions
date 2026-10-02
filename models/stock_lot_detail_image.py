# -*- coding: utf-8 -*-
"""Fotografías de DETALLE del lote (defectos, observaciones).

Van aparte de `stock.lot.image`, que son las fotos comerciales de la placa:
la galería muestra solo las comerciales; las de detalle acompañan a las
notas del lote (botón (i) del inventario visual) y se capturan desde la
app móvil, donde cualquier usuario puede señalar el defecto sobre la foto.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .utils.image_processor import ImageProcessor


class StockLotDetailImage(models.Model):
    _name = 'stock.lot.detail.image'
    _description = 'Fotografías de detalle del lote'
    _order = 'fecha_captura desc, id desc'

    name = fields.Char(string='Nombre', default='Detalle')
    lot_id = fields.Many2one(
        'stock.lot', string='Lote', required=True, ondelete='cascade', index=True)
    image = fields.Binary(string='Imagen', required=True, attachment=True)
    image_small = fields.Binary(
        string='Miniatura', compute='_compute_image_small', store=True)
    notas = fields.Text(string='Comentario')
    fecha_captura = fields.Datetime(
        string='Fecha de captura', default=fields.Datetime.now, index=True)
    user_id = fields.Many2one(
        'res.users', string='Capturó', default=lambda self: self.env.user)

    @api.depends('image')
    def _compute_image_small(self):
        ImageProcessor.compute_thumbnail(self)


class StockLotDetailPhotos(models.Model):
    _inherit = 'stock.lot'

    x_detalle_foto_ids = fields.One2many(
        'stock.lot.detail.image', 'lot_id', string='Fotos de detalle')
    x_cantidad_fotos_detalle = fields.Integer(
        string='Fotos de detalle (cantidad)',
        compute='_compute_x_cantidad_fotos_detalle', store=True)

    @api.depends('x_detalle_foto_ids')
    def _compute_x_cantidad_fotos_detalle(self):
        for lot in self:
            lot.x_cantidad_fotos_detalle = len(lot.x_detalle_foto_ids)

    def _som_detail_photos_payload(self, with_image=True):
        """Fotos de detalle del lote, de la más nueva a la más vieja."""
        self.ensure_one()
        photos = []
        for photo in self.sudo().x_detalle_foto_ids:
            photos.append({
                'id': photo.id,
                'name': photo.name or '',
                'image': photo.image if with_image else False,
                'notas': photo.notas or '',
                'fecha_captura': fields.Datetime.to_string(photo.fecha_captura)
                if photo.fecha_captura else '',
                'user': photo.user_id.name or '',
            })
        return photos

    @api.model
    def som_add_detail_photo(self, lot_id, image, name='', notas=''):
        """Alta de una foto de detalle. Abierta a CUALQUIER usuario interno
        (app móvil): se escribe con sudo para no depender de los permisos de
        inventario de quien encuentra el defecto."""
        if not self.env.user._is_internal():
            raise UserError(_('Solo usuarios internos pueden agregar fotos de detalle.'))
        lot = self.sudo().browse(int(lot_id)).exists()
        if not lot:
            raise UserError(_('El lote ya no existe.'))
        if not image:
            raise UserError(_('Falta la fotografía.'))
        photo = self.env['stock.lot.detail.image'].sudo().create({
            'lot_id': lot.id,
            'image': image,
            'name': name or _('Detalle %s') % lot.name,
            'notas': (notas or '').strip() or False,
            'user_id': self.env.user.id,
        })
        return photo.id

    @api.model
    def som_get_detail_photos(self, lot_id):
        lot = self.sudo().browse(int(lot_id)).exists()
        return lot._som_detail_photos_payload() if lot else []

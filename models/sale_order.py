# -*- coding: utf-8 -*-
# models/sale_order.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.picking_cleaner import PickingLotCleaner
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_selected_lots = fields.Many2many('stock.quant', string='Lotes Seleccionados')

    # MÁSCARA COMERCIAL — por VENTA, no por producto: el nombre con el que el
    # cliente conoce el material en ESTA operación (se vende "NEGRO SAN
    # GABRIEL" aunque el material real sea Santo Tomás). Nace en el quote, el
    # hold o la orden, se propaga en las conversiones y TODOS los documentos
    # (cotización, orden, entregas, pick tickets, remisiones, factura)
    # imprimen la máscara en lugar del nombre propio del material.
    x_mask_name = fields.Char(
        string='Máscara',
        copy=True,
        help='Nombre comercial del material para ESTA venta. Los documentos '
             'que genera el sistema imprimen la máscara en lugar del nombre '
             'real del producto. Se propaga de quote a hold y a la orden.',
    )

    @api.model
    def _som_pdf_image_src(self, b64_image, label=''):
        """Data URI COMPLETO y determinista para el PDF: siempre PNG.

        - wkhtmltopdf (QT WebKit) no renderiza WebP: cualquier formato que
          no sea PNG se re-codifica a PNG con Pillow.
        - El data URI se construye AQUÍ (mime fijo image/png): el template
          recibe un string terminado, sin image_data_uri ni procesamiento
          en QWeb — cero variables entre lo que produce Python y lo que
          incrusta el PDF.
        - Si Pillow no puede identificar la imagen, se regresa False (celda
          vacía) en lugar de un src roto (el 'puntito' de imagen rota)."""
        if not b64_image:
            return False
        import base64
        import io
        try:
            if isinstance(b64_image, str):
                b64_image = b64_image.encode()
            raw = base64.b64decode(b64_image)
        except Exception:
            _logger.warning(
                '[SOM PROPOSAL] Imagen %s: el binario no es base64 válido '
                '(¿bin_size?); se omite.', label or 'línea')
            return False
        # SVG: Pillow no lo abre (UnidentifiedImageError) pero el motor del
        # PDF sí lo incrusta como data URI — pasa directo, sin conversión.
        if raw.lstrip()[:1] == b'<' and b'<svg' in raw[:2048].lower():
            _logger.info(
                '[SOM PROPOSAL] Imagen %s: SVG, pasa directo al PDF.',
                label or 'línea')
            return 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode()
        from PIL import Image as PILImage
        # Odoo (odoo/tools/image.py) hace Image.preinit() y fija
        # Image._initialized = 2, con lo que Image.init() queda ANULADO:
        # dentro de un proceso de Odoo, Pillow solo tiene registrados BMP,
        # GIF, JPEG, PPM, PNG e Ico. Aunque el códec WebP esté instalado,
        # el plugin jamás se carga y open() responde UnidentifiedImageError
        # (por eso el mismo archivo abre en un python suelto y no en el
        # worker). Importar el plugin lo registra él mismo, vía el
        # register_open que corre a nivel de módulo.
        try:
            from PIL import WebPImagePlugin  # noqa: F401
        except ImportError:
            pass
        try:
            pil = PILImage.open(io.BytesIO(raw))
            fmt = (pil.format or '').upper()
            # Tope de 512px: el fallback a image_1920 (foto original) no
            # debe inflar el PDF con megapixeles que se imprimen a 100px.
            oversize = max(pil.size) > 512
            if fmt != 'PNG' or oversize:
                if oversize:
                    pil.thumbnail((512, 512))
                buffer = io.BytesIO()
                pil.convert('RGBA').save(buffer, format='PNG')
                b64_image = base64.b64encode(buffer.getvalue())
            _logger.info(
                '[SOM PROPOSAL] Imagen %s: formato origen %s, %s bytes b64.',
                label or 'línea', fmt or '?', len(b64_image))
            return 'data:image/png;base64,' + b64_image.decode()
        except Exception:
            # Nombrar el formato real por la firma de los bytes: es la
            # diferencia entre adivinar y saber qué instalar/corregir.
            if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
                # Pillow rechaza el archivo (UnidentifiedImageError) si el
                # chunk en 12:16 no es VP8 / VP8L / VP8X, aunque el códec
                # esté instalado. Y si el RIFF declara más bytes de los que
                # llegaron, el binario está TRUNCADO en el filestore: ahí el
                # arreglo es volver a subir la foto, no tocar Pillow.
                import struct
                try:
                    declared = struct.unpack('<I', raw[4:8])[0] + 8
                except Exception:
                    declared = -1
                fmt_hint = ('WEBP modo %r, RIFF declara %s bytes, plugin '
                            'registrado=%s' % (
                                raw[12:16], declared,
                                'WEBP' in PILImage.ID))
                if 0 < declared > len(raw):
                    fmt_hint += ' — TRUNCADO'
            elif raw[4:12] in (b'ftypavif', b'ftypavis'):
                fmt_hint = 'AVIF (Pillow necesita pillow-avif-plugin)'
            elif raw[4:8] == b'ftyp' and raw[8:12] in (
                    b'heic', b'heix', b'hevc', b'mif1'):
                fmt_hint = 'HEIC (foto de iPhone; Pillow necesita pillow-heif)'
            else:
                fmt_hint = 'desconocido, cabecera %r' % raw[:12]
            _logger.warning(
                '[SOM PROPOSAL] Imagen %s ilegible para el PDF — formato %s, '
                '%s bytes decodificados; se omite.',
                label or 'línea', fmt_hint, len(raw), exc_info=True)
            return False

    def som_proposal_image_src(self):
        """Src listo para <img> en el 'Resumen con imágenes': LA FOTO DEL
        PRODUCTO, exclusivamente (las fotos de lotes pertenecen al proceso
        de asignación; en una cotización solo se cotiza una cantidad).

        Público (sin guion bajo) para llamarse desde QWeb sin restricciones.
        bin_size=False es obligatorio: con bin_size activo el binario
        regresa el TAMAÑO ('12.5 KB') en lugar de la imagen."""
        self.ensure_one()
        if not self.product_id:
            return False
        # image_512 primero (miniatura ligera); si la derivada no está
        # materializada se cae a image_1920 — la MISMA fuente que usa el
        # wizard de sugerencias vía /web/image/.../image_1920 — y el helper
        # la reduce a 512px. Variante y plantilla, en ese orden.
        product = self.product_id.with_context(bin_size=False)
        template = product.product_tmpl_id.with_context(bin_size=False)
        found = False
        for record, fname in (
            (product, 'image_512'),
            (template, 'image_512'),
            (product, 'image_1920'),
            (template, 'image_1920'),
        ):
            img = record[fname]
            if not img:
                continue
            found = True
            src = self._som_pdf_image_src(
                img,
                label='%s [%s.%s]' % (product.display_name, record._name, fname),
            )
            # Si esta fuente es ilegible, la siguiente puede no serlo
            # (p. ej. derivada corrupta pero original sana).
            if src:
                return src
        if not found:
            _logger.info(
                '[SOM PROPOSAL] Producto %s (id %s) sin imagen en la ficha '
                '(image_512 e image_1920 vacíos en variante y plantilla).',
                product.display_name, product.id)
        return False

    def _som_default_line_description(self):
        self.ensure_one()
        try:
            return self._get_sale_order_line_multiline_description_sale()
        except Exception:
            return self.product_id.get_product_multiline_description_sale() \
                if self.product_id else (self.name or '')

    def _som_apply_mask_to_description(self, restore=False):
        """La descripción (name) es lo que imprimen los documentos estándar
        (cotización, factura, entregas): con máscara, la descripción ES la
        máscara; al quitarla, regresa la descripción comercial del producto.
        También se sincroniza description_picking de los movimientos vivos,
        que es lo que imprimen los documentos estándar de almacén."""
        for line in self:
            if line.display_type or not line.product_id:
                continue
            if line.x_mask_name:
                if (line.name or '') != line.x_mask_name:
                    line.name = line.x_mask_name
            elif restore:
                line.name = line._som_default_line_description()

            open_moves = line.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))
            if not open_moves:
                continue
            if line.x_mask_name:
                open_moves.write({'description_picking': line.x_mask_name})
            elif restore:
                for move in open_moves:
                    move.description_picking = move.product_id._get_description(
                        move.picking_type_id)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        masked = lines.filtered(lambda l: l.x_mask_name)
        if masked:
            masked._som_apply_mask_to_description()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'x_mask_name' in vals:
            # Escribir/limpiar la máscara re-sincroniza la descripción.
            self._som_apply_mask_to_description(restore=not vals.get('x_mask_name'))
        elif 'product_id' in vals:
            # Cambiar el producto recomputa la descripción con el nombre REAL:
            # la máscara debe volver a taparlo.
            self.filtered('x_mask_name')._som_apply_mask_to_description()
        return res


class StockMoveMask(models.Model):
    _inherit = 'stock.move'

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        # Movimientos que nacen DESPUÉS de escribir la máscara (entregas,
        # backorders): heredan el nombre comercial de la línea de venta para
        # que los documentos de almacén jamás muestren el nombre real.
        for move in moves:
            mask = move.sale_line_id.x_mask_name if move.sale_line_id else ''
            if mask and move.state not in ('done', 'cancel') \
                    and move.description_picking != mask:
                move.description_picking = mask
        return moves


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_project_id = fields.Many2one('project.project', string='Proyecto')
    x_architect_id = fields.Many2one('res.partner', string='Embajador')

    # PROPUESTA COMERCIAL SOM: logo del CLIENTE que se imprime junto al de
    # la compañía en el reporte de propuesta (solo cotizaciones).
    x_client_logo = fields.Binary(
        string='Logo del cliente',
        attachment=True,
        copy=False,
        help='Logo del cliente para la Propuesta Comercial SOM: se imprime '
             'en el encabezado del reporte junto al logo de la compañía.',
    )
    x_client_logo_filename = fields.Char(copy=False)

    def som_proposal_client_logo_src(self):
        """Src listo para <img> con el logo del cliente (data URI PNG
        construido en Python; bin_size=False obligatorio)."""
        self.ensure_one()
        logo = self.with_context(bin_size=False).x_client_logo
        return self.env['sale.order.line']._som_pdf_image_src(
            logo, label='logo cliente')
    
    @api.model
    def create_from_shopping_cart(self, partner_id=None, products=None, services=None, notes=None, pricelist_id=None, apply_tax=True, project_id=None, architect_id=None):
        if not partner_id or not products:
            raise UserError("Faltan parámetros: partner_id o products")
        
        if not pricelist_id:
            raise UserError("Debe especificar una lista de precios")
        
        pricelist = self.env['product.pricelist'].browse(pricelist_id)
        currency_code = pricelist.name
        
        from_hold_order = self.env.context.get('from_hold_order', False)
        
        if not from_hold_order:
            product_prices = {}
            for product in products:
                product_prices[str(product['product_id'])] = product['price_unit']
            
            auth_check = self.env['product.template'].check_price_authorization_needed(
                product_prices, 
                currency_code
            )
            
            if auth_check['needs_authorization']:
                product_groups = {}
                for product in products:
                    pid = product['product_id']
                    if pid not in product_groups:
                        product_rec = self.env['product.product'].browse(pid)
                        product_groups[pid] = {
                            'name': product_rec.display_name,
                            'lots': [],
                            'total_quantity': 0
                        }
                    
                    for quant_id in product['selected_lots']:
                        quant = self.env['stock.quant'].browse(quant_id)
                        product_groups[pid]['lots'].append({
                            'id': quant_id,
                            'lot_name': quant.lot_id.name,
                            'quantity': quant.quantity
                        })
                        product_groups[pid]['total_quantity'] += quant.quantity
                
                result = self.env['stock.quant'].create_price_authorization(
                    operation_type='sale',
                    partner_id=partner_id,
                    project_id=project_id,
                    selected_lots=[q_id for p in products for q_id in p['selected_lots']],
                    currency_code=currency_code,
                    product_prices=product_prices,
                    product_groups=product_groups,
                    notes=notes,
                    architect_id=architect_id
                )
                
                if result['success']:
                    return {
                        'success': False,
                        'needs_authorization': True,
                        'authorization_id': result['authorization_id'],
                        'authorization_name': result['authorization_name'],
                        'message': f'Solicitud de autorización {result["authorization_name"]} creada. Espere aprobación del autorizador.'
                    }
        
        company_id = self.env.context.get('company_id') or self.env.company.id
        
        # Comparación por CLIENTE COMERCIAL (igual que el HoldValidator
        # canónico): un hold a nombre del contacto de compras y una venta a
        # nombre de la empresa madre son el mismo cliente — antes se comparaba
        # el partner exacto y se rechazaba la venta legítima.
        order_partner = self.env['res.partner'].browse(partner_id)
        order_commercial = order_partner.commercial_partner_id

        for product in products:
            for quant_id in product['selected_lots']:
                quant = self.env['stock.quant'].browse(quant_id)
                if quant.x_tiene_hold:
                    hold_partner = quant.x_hold_activo_id.partner_id
                    if hold_partner.commercial_partner_id != order_commercial:
                        raise UserError(f"El lote {quant.lot_id.name} está apartado para {hold_partner.name}")
        
        sale_order = self.with_company(company_id).create({
            'partner_id': partner_id,
            'note': notes or '',
            'pricelist_id': pricelist_id,
            'company_id': company_id,
        })
        
        for product in products:
            product_rec = self.env['product.product'].browse(product['product_id'])
            
            if apply_tax and product_rec.taxes_id:
                tax_ids = [(6, 0, product_rec.taxes_id.ids)]
            else:
                tax_ids = [(5, 0, 0)]
            
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product['product_id'],
                'product_uom_qty': product['quantity'],
                'price_unit': product['price_unit'],
                'tax_ids': tax_ids,
                'x_selected_lots': [(6, 0, product['selected_lots'])],
                'company_id': company_id,
            }
            # Máscara comercial (hold → SO): el nombre personalizado de la
            # venta viaja con la línea; el hook de create la aplica al name.
            if product.get('mask_name'):
                line_vals['x_mask_name'] = product['mask_name']

            self.env['sale.order.line'].with_company(company_id).create(line_vals)
        
        if services:
            for service in services:
                service_product = self.env['product.product'].browse(service['product_id'])
                
                if apply_tax and service_product.taxes_id:
                    tax_ids = [(6, 0, service_product.taxes_id.ids)]
                else:
                    tax_ids = [(5, 0, 0)]
                
                service_vals = {
                    'order_id': sale_order.id,
                    'product_id': service['product_id'],
                    'product_uom_qty': service['quantity'],
                    'price_unit': service['price_unit'],
                    'tax_ids': tax_ids,
                    'company_id': company_id,
                }
                if service.get('mask_name'):
                    service_vals['x_mask_name'] = service['mask_name']

                self.env['sale.order.line'].with_company(company_id).create(service_vals)
        
        sale_order.with_company(company_id).with_context(
            stone_transient_auto_assign=True,
            skip_duplicate_lot_validation=True,
            skip_hold_validation=True,
            skip_picking_clean=False,
        ).action_confirm()
        
        for line in sale_order.order_line:
            if line.x_selected_lots:
                picking = line.move_ids.mapped('picking_id')
                if picking:
                    self._assign_specific_lots(picking, line.product_id, line.x_selected_lots)
        
        if not from_hold_order:
            self.env['shopping.cart'].clear_cart()
        
        return {
            'success': True,
            'order_id': sale_order.id,
            'order_name': sale_order.name
        }
    
    def _assign_specific_lots(self, picking, product, quants):
        for move in picking.move_ids.filtered(lambda m: m.product_id == product):
            if move.move_line_ids:
                # Primero liberar la reserva nativa. Un unlink directo puede dejar
                # stock.quant.reserved_quantity inflado y provocar duplicidades en
                # la siguiente asignación exacta.
                move.with_context(
                    skip_duplicate_lot_validation=True,
                    skip_hold_validation=True,
                    stone_transient_auto_assign_cleanup=True,
                )._do_unreserve()

                remaining_lines = move.move_line_ids.exists()
                if remaining_lines:
                    remaining_lines.with_context(
                        skip_duplicate_lot_validation=True,
                        skip_hold_validation=True,
                        stone_transient_auto_assign_cleanup=True,
                    ).unlink()

            move_line_model = self.env['stock.move.line'].with_context(
                skip_hold_validation=True,
            )
            
            for quant in quants:
                move_line_model.create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': product.id,
                    'lot_id': quant.lot_id.id,
                    'location_id': quant.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': quant.quantity,
                    'product_uom_id': move.product_uom.id,
                })
    
    def action_confirm(self):
        _logger.info("Confirmando órdenes: %s", self.mapped('name'))
        
        all_partner_ids = self.mapped('partner_id.id')
        context = dict(self.env.context)
        if all_partner_ids:
            if len(all_partner_ids) == 1:
                context['allowed_partner_id'] = all_partner_ids[0]
            else:
                context['allowed_partner_ids'] = all_partner_ids
        
        res = super(SaleOrder, self.with_context(**context)).action_confirm()
        
        # MODIFICADO: Solo limpiar si NO viene de sale_stone_selection
        if not self.env.context.get('skip_picking_clean'):
            self._clear_auto_assigned_lots()
        else:
            _logger.info("[STONE] Limpieza de lotes omitida por contexto skip_picking_clean")
        
        return res
    
    def _clear_auto_assigned_lots(self):
        # MODIFICADO: Obtener lotes protegidos del contexto
        protected_lot_ids = self.env.context.get('protected_lot_ids', [])
        
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids, protected_lot_ids=protected_lot_ids)
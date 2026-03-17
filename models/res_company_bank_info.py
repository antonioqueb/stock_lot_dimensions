# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompanyBankInfo(models.Model):
    _name = 'res.company.bank.info'
    _description = 'Datos Bancarios Comerciales por Compañía'
    _order = 'sequence, id'

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        ondelete='cascade',
        index=True,
        default=lambda self: self.env.company,
    )

    name = fields.Char(
        string='Etiqueta',
        required=True,
        help='Ejemplo: Banorte USD / Banorte MXN'
    )

    bank_name = fields.Char(
        string='Banco',
        required=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True
    )

    account_holder = fields.Char(
        string='Titular',
        required=True
    )

    account_number = fields.Char(
        string='Cuenta'
    )

    clabe = fields.Char(
        string='CLABE'
    )

    swift = fields.Char(
        string='SWIFT'
    )

    branch = fields.Char(
        string='Sucursal'
    )

    notes = fields.Text(
        string='Notas'
    )
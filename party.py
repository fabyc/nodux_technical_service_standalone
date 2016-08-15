#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
#! -*- coding: utf8 -*-
from trytond.pool import *
import logging
from importlib import import_module
from trytond.model import ModelView, ModelSQL, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pyson import Bool, Eval, Id
from trytond.transaction import Transaction
import re

__all__ = ['Party', 'Company']
__metaclass__ = PoolMeta


class Party:
    __name__ = 'party.party'

    type_document = fields.Selection([
                ('', ''),
                ('04', 'RUC'),
                ('05', 'Cedula'),
                ('06', 'Pasaporte'),
                ('07', 'Consumidor Final'),
            ], 'Type Document', states={
                'readonly': ~Eval('active', True),
            },  depends=['active'])

    @staticmethod
    def default_type_document():
        return '05'

    @classmethod
    def search_rec_name(cls, name, clause):
        parties = cls.search([
                ('vat_number',) + tuple(clause[1:]),
                ], limit=1)
        if parties:
            return [('vat_number',) + tuple(clause[1:])]
        return [('name',) + tuple(clause[1:])]
        
class Company:
    __name__ = 'company.company'

    @classmethod
    def default_currency(cls):
        Currency = Pool().get('currency.currency')
        usd= Currency.search([('code','=','USD')])
        return usd[0].id

    @staticmethod
    def default_timezone():
        return 'America/Guayaquil'

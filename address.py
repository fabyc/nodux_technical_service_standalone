#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
#! -*- coding: utf8 -*-
from trytond.pool import *
from trytond.model import fields
from trytond.pyson import Eval
from trytond.pyson import Id
from trytond.pyson import Bool, Eval

__all__ = ['Address']
__metaclass__ = PoolMeta

class Address:
    __name__ = 'party.address'

    @staticmethod
    def default_country():
        return Id('country', 'ec').pyson()

    @staticmethod
    def default_subdivision():
        Subdivision = Pool().get('country.subdivision')
        sub= Subdivision.search([('code','=','EC-L')])
        return sub[0].id

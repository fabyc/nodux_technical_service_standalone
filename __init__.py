#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from .service import *
from .account import *
from .party import *

def register():
    Pool.register(
        FiscalYear,
        Period,
        Periferic,
        Service,
        ServiceLine,
        HistoryLine,
        Party,
        Company,
        module='nodux_technical_service', type_='model')
    Pool.register(
        ServiceReport,
        module="nodux_technical_service", type_='report')

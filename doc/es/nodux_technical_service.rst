=============
Servicio Técnico
=============

Módulo para realizar ingresos de Servicio Técnico, es adaptable y permite
ingreso de marcas, periféricos, encargado, fecha (recepción-entrega), además
de llevar un historial de las actividades que el encargado a realizado durante 
la revisión del periférico.

El servicio puede estar en los siguientes estados:
-Pendiente : cuando que se hace el registro del servicio
-En revisión : cuando el encargado (técnico) ha iniciado con la revisión puede
cambiar el estado del servicio.
-Ingreso por garantía: Se mostrarán todos los ingresos que se hayan hecho por garantía
-Listo: si la revisión del periférico culminó con éxito se puede pasar al estado Listo
-No cubre garantia: Cuando el  periférico ingresa por Garantía se puede indicar si el 
arreglo no está cubierto por la garantia.
-Sin solución: Cuando se ha hecho la revisión del producto y no se encuentra una solución
se marca en este estado
-Entregar: Sea cual haya sido el resultado del periférico (Listo, No cubre Garantía, Sin 
Solución) se debe hacer la entrega al cliente en el momento que se marca este estado, ya 
no se puede modificar los datos del servicio (excepto Historial), ni eliminarlo.

Módulo para realizar ingresos de Servicio Técnico a Domicilio, es adaptable y permite
ingreso de la fecha que se supone se hará la visita, el cliente y el monto aproximado.

El servicio puede estar en los siguientes estados:
-Pendiente : cuando que se hace el registro del servicio a domicilio.
-Listo: cuando se haya efectuado la visita.

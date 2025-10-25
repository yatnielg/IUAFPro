(function() {
  function toggleCampos() {
    const sel = document.getElementById('id_tipo_descuento');
    if (!sel) return;

    const pctRow = document.querySelector('.form-row.field-porcentaje_descuento') ||
                   document.querySelector('#id_porcentaje_descuento')?.closest('div');
    const montoRow = document.querySelector('.form-row.field-monto_descuento') ||
                     document.querySelector('#id_monto_descuento')?.closest('div');

    const tipo = sel.value;
    if (pctRow) pctRow.style.display = (tipo === 'porcentaje') ? '' : 'none';
    if (montoRow) montoRow.style.display = (tipo === 'monto') ? '' : 'none';
  }

  document.addEventListener('DOMContentLoaded', function() {
    toggleCampos();
    const sel = document.getElementById('id_tipo_descuento');
    if (sel) sel.addEventListener('change', toggleCampos);
  });
})();

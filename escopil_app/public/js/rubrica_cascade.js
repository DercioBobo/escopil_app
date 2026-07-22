const RUBRICA_CASCADE_DOCTYPES = ['Material Request', 'Purchase Order', 'Purchase Invoice'];

const RUBRICA_AUTOMATIC_FILTER = () => ({
	filters: {
		allowed_source: ['in', ['Automático (Fatura/PO)', 'Ambos']],
		disabled: 0,
	},
});

frappe.ui.form.on(RUBRICA_CASCADE_DOCTYPES, {
	refresh(frm) {
		frm.set_query('custom_rubrica', RUBRICA_AUTOMATIC_FILTER);
		frm.set_query('custom_rubrica', 'items', RUBRICA_AUTOMATIC_FILTER);
	},
	custom_rubrica(frm) {
		if (!frm.doc.custom_rubrica) return;
		(frm.doc.items || []).forEach((item) => {
			frappe.model.set_value(item.doctype, item.name, 'custom_rubrica', frm.doc.custom_rubrica);
		});
	},
});

frappe.ui.form.on('Material Request Item', {
	items_add(frm, cdt, cdn) {
		set_row_rubrica_default(frm, cdt, cdn);
	},
});
frappe.ui.form.on('Purchase Order Item', {
	items_add(frm, cdt, cdn) {
		set_row_rubrica_default(frm, cdt, cdn);
	},
});
frappe.ui.form.on('Purchase Invoice Item', {
	items_add(frm, cdt, cdn) {
		set_row_rubrica_default(frm, cdt, cdn);
	},
});

function set_row_rubrica_default(frm, cdt, cdn) {
	if (!frm.doc.custom_rubrica) return;
	frappe.model.set_value(cdt, cdn, 'custom_rubrica', frm.doc.custom_rubrica);
}

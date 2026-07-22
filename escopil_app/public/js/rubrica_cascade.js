const RUBRICA_CASCADE_DOCTYPES = ['Material Request', 'Purchase Order', 'Purchase Invoice'];

frappe.ui.form.on(RUBRICA_CASCADE_DOCTYPES, {
	custom_rubrica(frm) {
		if (!frm.doc.custom_rubrica) return;
		(frm.doc.items || []).forEach((item) => {
			item.custom_rubrica = frm.doc.custom_rubrica;
		});
		frm.refresh_field('items');
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

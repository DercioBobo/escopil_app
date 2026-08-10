const STOCK_ENTRY_RUBRICA_OPTIONS = ['Consumiveis', 'Material de Safety'];

frappe.ui.form.on('Stock Entry', {
	refresh(frm) {
		frm.set_query('custom_rubrica', () => ({
			filters: {
				rubrica_name: ['in', STOCK_ENTRY_RUBRICA_OPTIONS],
				disabled: 0,
			},
		}));
	},
});

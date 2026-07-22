frappe.pages['project-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Project Dashboard',
		single_column: true
	});

	frappe.require('/assets/escopil_app/css/project_dashboard.css', () => {
		frappe.project_dashboard = new ProjectDashboard(page);
	});
};

frappe.pages['project-dashboard'].on_page_show = function () {
	if (frappe.project_dashboard) {
		frappe.project_dashboard.check_route_options();
	}
};

class ProjectDashboard {
	constructor(page) {
		this.page = page;
		this.setup();
	}

	setup() {
		$(this.page.body).html(`
			<div class="project-dashboard">
				<div class="pd-filter-bar"></div>
				<div class="pd-content"></div>
			</div>
		`);

		this.$wrapper = $(this.page.body).find('.project-dashboard');
		this.$content = this.$wrapper.find('.pd-content');

		this.project_control = frappe.ui.form.make_control({
			parent: this.$wrapper.find('.pd-filter-bar').get(0),
			df: {
				fieldtype: 'Link',
				fieldname: 'project',
				label: 'Projeto',
				options: 'Project',
				onchange: () => {
					const project = this.project_control.get_value();
					if (project) {
						this.load(project);
					} else {
						this.render_empty();
					}
				}
			},
			render_input: true,
		});
		this.project_control.refresh();

		if (!this.check_route_options()) {
			this.render_empty();
		}
	}

	// consumes frappe.route_options.project so a "Painel de Orçamento" button
	// on the Project form can deep-link straight into this page
	check_route_options() {
		const options = frappe.route_options;
		if (options && options.project) {
			frappe.route_options = null;
			this.project_control.set_value(options.project);
			return true;
		}
		return false;
	}

	render_empty() {
		this.$content.html(`
			<div class="pd-empty">Selecione um Projeto para ver o painel de orçamento.</div>
		`);
	}

	load(project) {
		frappe.call({
			method: 'escopil_app.project_management.page.project_dashboard.project_dashboard.get_dashboard_data',
			args: { project },
			freeze: true,
			callback: (r) => {
				if (r.message) {
					this.render(r.message);
				}
			}
		});
	}

	// variance = actual vs. the rubrica's own monthly forecast; class carries
	// how far under/over budget the cell is, alpha scales with severity
	variance_class(actual, forecast) {
		if (!forecast) {
			return actual ? { cls: 'pd-variance-over', alpha: 0.16 } : { cls: '', alpha: 0 };
		}
		const ratio = actual / forecast;
		if (ratio <= 0.9) {
			const severity = Math.min((0.9 - ratio) / 0.9, 1);
			return { cls: 'pd-variance-under', alpha: 0.08 + severity * 0.18 };
		}
		if (ratio > 1.1) {
			const severity = Math.min((ratio - 1.1) / 1.1, 1);
			return { cls: 'pd-variance-over', alpha: 0.08 + severity * 0.22 };
		}
		return { cls: '', alpha: 0 };
	}

	render(data) {
		const fmt = (v) => format_currency(v || 0);
		const pct = (v) => (v || 0).toFixed(1) + '%';
		const months = data.months;
		const n_months = months.length || 1;

		const total_cost = months.reduce((s, m) => s + (data.totals[m.key] || 0), 0);
		const total_billing = months.reduce((s, m) => s + (data.billing[m.key] || 0), 0);
		const total_margin = total_billing - total_cost;
		const total_margin_pct = total_billing ? (total_margin / total_billing * 100) : 0;
		const budget_total = (data.total_forecast || 0) * n_months;

		const strip = `
			<div class="pd-strip">
				<div class="pd-stat">
					<span class="pd-stat-label">Orçamento do Período</span>
					<span class="pd-stat-value">${fmt(budget_total)}</span>
					<span class="pd-stat-sub">${fmt(data.total_forecast)} / mês</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Custos Reais</span>
					<span class="pd-stat-value">${fmt(total_cost)}</span>
					<span class="pd-stat-sub">${budget_total ? pct(total_cost / budget_total * 100) : '—'} do orçamento</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Valor a Cobrar</span>
					<span class="pd-stat-value">${fmt(total_billing)}</span>
					<span class="pd-stat-sub">&nbsp;</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Margem</span>
					<span class="pd-stat-value ${total_margin >= 0 ? 'is-positive' : 'is-negative'}">${fmt(total_margin)}</span>
					<span class="pd-stat-sub">${pct(total_margin_pct)}</span>
				</div>
			</div>
		`;

		const head = `
			<tr>
				<th class="pd-col-rubrica">Rubrica</th>
				<th class="text-right">Previsão Mensal</th>
				<th class="text-right">Peso</th>
				${months.map(m => `<th class="text-right">${frappe.utils.escape_html(m.label)}</th>`).join('')}
			</tr>
		`;

		const body = data.rubricas.map(r => `
			<tr>
				<td class="pd-col-rubrica">${frappe.utils.escape_html(r.rubrica)}</td>
				<td class="text-right">${fmt(r.monthly_forecast)}</td>
				<td class="text-right">
					<div class="pd-weight">
						<span>${pct(r.weight * 100)}</span>
						<span class="pd-weight-bar"><span style="width:${Math.min(r.weight * 100, 100)}%"></span></span>
					</div>
				</td>
				${months.map(m => {
					const actual = r.actuals[m.key] || 0;
					const v = this.variance_class(actual, r.monthly_forecast);
					const style = v.cls ? ` style="--pd-alpha:${v.alpha}"` : '';
					return `<td class="text-right ${v.cls}"${style}>${fmt(actual)}</td>`;
				}).join('')}
			</tr>
		`).join('');

		const total_row = `
			<tr class="pd-row-total">
				<td class="pd-col-rubrica text-left" colspan="3">Total de Custos</td>
				${months.map(m => `<td class="text-right">${fmt(data.totals[m.key])}</td>`).join('')}
			</tr>
		`;

		const billing_row = `
			<tr class="pd-row-billing">
				<td class="text-left" colspan="3">Valor a Cobrar</td>
				${months.map(m => `<td class="text-right">${fmt(data.billing[m.key])}</td>`).join('')}
			</tr>
		`;

		const margin_row = `
			<tr class="pd-row-margin">
				<td class="text-left" colspan="3">Margem</td>
				${months.map(m => {
					const margin = data.margin[m.key] || 0;
					const cls = margin > 0 ? 'pd-variance-under' : (margin < 0 ? 'pd-variance-over' : '');
					return `<td class="text-right ${cls}">${fmt(margin)}</td>`;
				}).join('')}
			</tr>
		`;

		const margin_pct_row = `
			<tr class="pd-row-margin-pct">
				<td class="text-left" colspan="3">Margem %</td>
				${months.map(m => {
					const v = data.margin_pct[m.key] || 0;
					const cls = v > 0 ? 'pd-variance-under' : (v < 0 ? 'pd-variance-over' : '');
					return `<td class="text-right ${cls}">${pct(v)}</td>`;
				}).join('')}
			</tr>
		`;

		this.$content.html(`
			<div class="pd-fade">
				${strip}
				<h6 class="pd-eyebrow">Rubricas do Orçamento</h6>
				<div class="pd-table-wrap">
					<table class="pd-ledger">
						<thead>${head}</thead>
						<tbody>${body}${total_row}${billing_row}${margin_row}${margin_pct_row}</tbody>
					</table>
				</div>
			</div>
		`);
	}
}

frappe.pages['next-ai'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Next AI',
		single_column: true,
	});

	frappe.require('/assets/escopil_app/css/next_ai.css', () => {
		frappe.next_ai = new NextAI(page);
	});
};

const SECTION_META = {
	invoicing: { label: 'Faturação', ready: true },
	purchasing: { label: 'Compras', ready: false },
	stock: { label: 'Stock', ready: false },
	projects: { label: 'Projetos', ready: false },
};
const SECTION_ORDER = ['invoicing', 'purchasing', 'stock', 'projects'];

class NextAI {
	constructor(page) {
		this.page = page;
		this.sections = [];
		this.activeSectionId = 'invoicing';
		this.trail = [];
		this.asked = new Set();
		this.setup();
	}

	setup() {
		$(this.page.body).html(`
			<div class="next-ai">
				<div class="na-rail"></div>
				<div class="na-main">
					<div class="na-trail"></div>
					<div class="na-thread"></div>
					<div class="na-suggestions"></div>
					<form class="na-inputbar">
						<input type="text" class="na-input" placeholder="Escreva a sua pergunta..." autocomplete="off" />
						<button type="submit" class="na-send" aria-label="Enviar">↑</button>
					</form>
				</div>
			</div>
		`);

		this.$wrapper = $(this.page.body).find('.next-ai');
		this.$rail = this.$wrapper.find('.na-rail');
		this.$trail = this.$wrapper.find('.na-trail');
		this.$thread = this.$wrapper.find('.na-thread');
		this.$suggestions = this.$wrapper.find('.na-suggestions');
		this.$input = this.$wrapper.find('.na-input');

		this.$wrapper.find('.na-inputbar').on('submit', (e) => {
			e.preventDefault();
			this.handle_free_text();
		});

		this.page.add_inner_button(__('Reiniciar conversa'), () => this.restart());

		frappe.call('escopil_app.next_ai.page.next_ai.next_ai.get_sections').then((r) => {
			this.sections = r.message || [];
			this.render_rail();
			this.render_welcome();
			this.render_suggestions(this.current_section_prompts());
		});
	}

	current_section_prompts() {
		const section = this.sections.find((s) => s.id === this.activeSectionId);
		return section ? section.prompts : [];
	}

	render_rail() {
		this.$rail.empty();
		this.$rail.append(`<div class="na-brand">Next AI</div>`);

		SECTION_ORDER.forEach((id) => {
			const meta = SECTION_META[id];
			const active = id === this.activeSectionId ? 'is-active' : '';
			const disabled = meta.ready ? '' : 'is-disabled';
			const badge = meta.ready ? '' : '<span class="na-soon">Em breve</span>';
			const $btn = $(`
				<button type="button" class="na-section ${active} ${disabled}">
					<span>${frappe.utils.escape_html(meta.label)}</span>
					${badge}
				</button>
			`);
			if (meta.ready) {
				$btn.on('click', () => this.switch_section(id));
			}
			this.$rail.append($btn);
		});
	}

	switch_section(id) {
		if (id === this.activeSectionId) return;
		this.activeSectionId = id;
		this.restart();
	}

	restart() {
		this.trail = [];
		this.asked = new Set();
		this.$thread.empty();
		this.render_rail();
		this.render_welcome();
		this.render_suggestions(this.current_section_prompts());
	}

	render_welcome() {
		const label = SECTION_META[this.activeSectionId].label;
		this.$thread.empty();
		this.$trail.empty();
		this.append_bot_html(`
			<p>Olá! Sou o assistente <strong>Next AI</strong>.</p>
			<p>Escolha uma pergunta sobre <strong>${frappe.utils.escape_html(label)}</strong> para começar.</p>
		`);
	}

	render_trail() {
		if (!this.trail.length) {
			this.$trail.empty();
			return;
		}
		const crumbs = this.trail.map((t, idx) => {
			const isLast = idx === this.trail.length - 1;
			return `<span class="na-crumb ${isLast ? 'is-last' : ''}" data-idx="${idx}">${frappe.utils.escape_html(t)}</span>`;
		});
		this.$trail.html(crumbs.join('<span class="na-crumb-sep">›</span>'));
	}

	// --- asking flow -------------------------------------------------------

	prompt_key(id, params) {
		return id + '::' + JSON.stringify(params || {});
	}

	ask_prompt(prompt_id, label, params) {
		this.asked.add(this.prompt_key(prompt_id, params));
		this.append_user_bubble(label);
		this.trail.push(label);
		this.render_trail();
		this.render_suggestions([]);

		const $typing = this.append_typing_indicator();

		frappe.call({
			method: 'escopil_app.next_ai.page.next_ai.next_ai.ask',
			args: { prompt_id, params: params || {} },
			callback: (r) => {
				$typing.remove();
				const result = r.message || {};
				this.append_bot_result(result);
				this.render_suggestions(result.follow_ups || []);
			},
			error: () => {
				$typing.remove();
				this.append_bot_html(`<p>Não consegui obter essa resposta agora. Tente novamente.</p>`);
				this.render_suggestions(this.current_section_prompts());
			},
		});
	}

	handle_free_text() {
		const raw = this.$input.val();
		const text = (raw || '').trim();
		if (!text) return;
		this.$input.val('');

		const match = this.match_prompt(text);
		if (match) {
			this.ask_prompt(match.id, match.label);
			return;
		}

		this.append_user_bubble(text);
		this.append_bot_html(`
			<p>Ainda não tenho uma resposta pronta para essa pergunta.</p>
			<p>Escolha uma das sugestões abaixo:</p>
		`);
		this.render_suggestions(this.current_section_prompts());
	}

	match_prompt(text) {
		const ACCENTS = {
			'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
			'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
			'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
			'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
			'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
			'ç': 'c',
		};
		const norm = (s) => (s || '')
			.toLowerCase()
			.split('')
			.map((ch) => ACCENTS[ch] || ch)
			.join('')
			.replace(/[^a-z0-9 ]/g, '')
			.trim();
		const needle = norm(text);
		return this.current_section_prompts().find((p) => {
			const hay = norm(p.label);
			return hay === needle || hay.includes(needle) || needle.includes(hay);
		});
	}

	// --- rendering -----------------------------------------------------------

	append_user_bubble(label) {
		const $row = $(`
			<div class="na-row na-row-user">
				<div class="na-bubble na-bubble-user">${frappe.utils.escape_html(label)}</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
	}

	append_typing_indicator() {
		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot na-typing">
					<span></span><span></span><span></span>
				</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	append_bot_html(html, extraClass) {
		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot ${extraClass || ''}">${html}</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	append_bot_result(result) {
		const blocks = result.blocks || [];
		const isWide = blocks.some((b) => b.type === 'table' || b.type === 'comparison' || b.type === 'bar');

		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot ${isWide ? 'na-bubble-wide' : ''}"></div>
			</div>
		`);
		const $bubble = $row.find('.na-bubble');

		if (result.title) {
			$bubble.append(`<div class="na-answer-title">${frappe.utils.escape_html(result.title)}</div>`);
		}
		blocks.forEach((block) => $bubble.append(this.render_block(block)));

		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	render_block(block) {
		if (block.type === 'metric') {
			return $(`
				<div class="na-metric">
					<div class="na-metric-label">${frappe.utils.escape_html(block.label)}</div>
					<div class="na-metric-value">${frappe.utils.escape_html(block.value)}</div>
				</div>
			`);
		}
		if (block.type === 'comparison') {
			return this.render_comparison_block(block);
		}
		if (block.type === 'table') {
			return this.render_table_block(block);
		}
		if (block.type === 'text') {
			return $(`<p class="na-text">${frappe.utils.escape_html(block.text)}</p>`);
		}
		if (block.type === 'kpi_grid') {
			const items = (block.items || []).map((it) => `
				<div class="na-kpi">
					<div class="na-metric-label">${frappe.utils.escape_html(it.label)}</div>
					<div class="na-metric-value na-metric-value-sm">${frappe.utils.escape_html(it.value)}</div>
				</div>
			`).join('');
			return $(`<div class="na-kpi-grid">${items}</div>`);
		}
		if (block.type === 'bar') {
			return $(this.render_bar_html(block));
		}
		if (block.type === 'trend') {
			return $(this.render_trend_html(block));
		}
		return $();
	}

	render_comparison_block(block) {
		const items = (block.items || []).map((it) => `
			<div class="na-compare-item">
				<div class="na-metric-label">${frappe.utils.escape_html(it.label)}</div>
				<div class="na-metric-value na-metric-value-sm">${frappe.utils.escape_html(it.value)}</div>
			</div>
		`).join('<div class="na-compare-arrow">→</div>');

		let delta = '';
		if (block.delta_pct !== null && block.delta_pct !== undefined) {
			const up = block.delta_pct >= 0;
			delta = `
				<div class="na-delta ${up ? 'is-up' : 'is-down'}">
					${up ? '▲' : '▼'} ${Math.abs(block.delta_pct).toFixed(1)}%
				</div>
			`;
		}
		return $(`<div class="na-compare-block"><div class="na-compare">${items}</div>${delta}</div>`);
	}

	render_table_block(block) {
		const head = (block.columns || []).map((c) => `<th>${frappe.utils.escape_html(c)}</th>`).join('');
		const rowsHtml = (block.rows || []).map((row, idx) => `
			<tr data-row-idx="${idx}">${row.map((cell) => `<td>${frappe.utils.escape_html(String(cell))}</td>`).join('')}</tr>
		`).join('');

		const $block = $(`
			<div class="na-table-block">
				<div class="na-table-wrap">
					<table class="na-table">
						<thead><tr>${head}</tr></thead>
						<tbody>${rowsHtml}</tbody>
					</table>
				</div>
			</div>
		`);

		if (block.row_prompt_id) {
			const rowParams = block.row_params || [];
			const rowLabels = block.row_labels || [];
			$block.find('tbody tr')
				.addClass('na-row-clickable')
				.attr('title', __('Ver detalhe'))
				.on('click', (e) => {
					const idx = Number($(e.currentTarget).attr('data-row-idx'));
					this.ask_prompt(block.row_prompt_id, rowLabels[idx] || __('Ver detalhe'), rowParams[idx] || {});
				});
		}

		if (block.load_more) {
			const lm = block.load_more;
			const $more = $(`
				<button type="button" class="na-load-more">
					${frappe.utils.escape_html(lm.label)}
					<span class="na-load-more-hint">${__('faltam {0}', [lm.remaining])}</span>
				</button>
			`);
			$more.on('click', () => this.ask_prompt(lm.prompt_id, lm.label, lm.params));
			$block.append($more);
		}

		return $block;
	}

	render_bar_html(block) {
		const items = block.items || [];
		if (!items.length) return '';
		const max = block.max || Math.max(...items.map((it) => Number(it.value) || 0), 1);

		const rows = items.map((it) => {
			const pct = Math.max(0, Math.min(100, ((Number(it.value) || 0) / max) * 100));
			return `
				<div class="na-bar-row">
					<div class="na-bar-label" title="${frappe.utils.escape_html(it.label)}">${frappe.utils.escape_html(it.label)}</div>
					<div class="na-bar-track">
						<div class="na-bar-fill" style="width:${pct}%"></div>
					</div>
					<div class="na-bar-value">${frappe.utils.escape_html(it.display || String(it.value))}</div>
				</div>
			`;
		}).join('');

		return `<div class="na-bar-chart">${rows}</div>`;
	}

	render_trend_html(block) {
		const points = block.points || [];
		if (!points.length) return '';

		const values = points.map((p) => Number(p.value) || 0);
		const min = Math.min(...values, 0);
		const max = Math.max(...values, 1);
		const range = max - min || 1;
		const W = 300;
		const H = 70;
		const PAD = 6;
		const step = points.length > 1 ? (W - PAD * 2) / (points.length - 1) : 0;

		const coords = points.map((p, i) => {
			const x = PAD + step * i;
			const y = H - PAD - (((Number(p.value) || 0) - min) / range) * (H - PAD * 2);
			return [x, y];
		});
		const path = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
		const dots = coords.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" class="na-trend-dot"></circle>`).join('');
		const labels = points.map((p) => `<span>${frappe.utils.escape_html(p.label)}</span>`).join('');
		const title = block.label ? `<div class="na-metric-label">${frappe.utils.escape_html(block.label)}</div>` : '';

		return `
			<div class="na-trend">
				${title}
				<svg viewBox="0 0 ${W} ${H}" class="na-trend-svg" preserveAspectRatio="none">
					<path d="${path}" class="na-trend-line" fill="none"></path>
					${dots}
				</svg>
				<div class="na-trend-labels">${labels}</div>
			</div>
		`;
	}

	render_suggestions(prompts) {
		this.$suggestions.empty();

		const unseen = (prompts || []).filter((p) => !this.asked.has(this.prompt_key(p.id, p.params)));
		const fallback = unseen.length ? unseen : this.current_section_prompts().filter(
			(p) => !this.asked.has(this.prompt_key(p.id, p.params))
		);

		if (!fallback.length) {
			const $pill = $(`<button type="button" class="na-pill na-pill-restart">${__('Recomeçar')}</button>`);
			$pill.on('click', () => this.restart());
			this.$suggestions.append($pill);
			return;
		}

		fallback.forEach((p) => {
			const $pill = $(`<button type="button" class="na-pill">${frappe.utils.escape_html(p.label)}</button>`);
			$pill.on('click', () => this.ask_prompt(p.id, p.label, p.params));
			this.$suggestions.append($pill);
		});
	}

	scroll_to_bottom() {
		this.$thread.animate({ scrollTop: this.$thread.prop('scrollHeight') }, 150);
	}
}

"""
Testes de acessibilidade (a11y) — validação estrutural dos componentes React
Foca em problemas que afetam leitores de tela e navegação por teclado.
"""
import re
from pathlib import Path

_BASE = Path(__file__).parent.parent
_FE = _BASE / "frontend" / "app"

# As páginas /<slug> são wrappers finos (dynamic import); a heurística de
# a11y inspeciona o módulo real da tool, não o wrapper.
_LINKEDIN = _FE / "analise-linkedin" / "linkedin.tsx"
_LAYOUT = _FE / "layout.tsx"
_APP_SHELL = _FE / "components" / "AppShell.tsx"
_LAYOUT_COMP = _FE / "components" / "Layout.tsx"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ============================================================================
# Component structure checks via source inspection
# ============================================================================

class TestA11yStructure:
    """Verifica padrões básicos de acessibilidade nos arquivos-fonte."""

    def test_layout_has_main_content(self):
        """Layout deve ter tag main (ou motion.main) para conteúdo semântico."""
        appshell_content = read_file(_APP_SHELL)
        # O main está no AppShell, não no layout
        has_main = bool(re.search(r"<(motion\.)?main", appshell_content, re.IGNORECASE))
        assert has_main, "AppShell deve conter tag <main> (ou <motion.main>) para conteúdo principal"

    def test_appshell_has_navigate_buttons(self):
        """AppShell/Layout deve ter botões de navegação (button ou motion.button)."""
        appshell_content = read_file(_APP_SHELL)
        layout_content = read_file(_LAYOUT_COMP)
        has_buttons = bool(re.search(r"<button|<motion\.button", appshell_content, re.IGNORECASE)) or \
                      bool(re.search(r"<button|<motion\.button", layout_content, re.IGNORECASE))
        assert has_buttons, "AppShell/Layout deve conter botões de navegação (button ou motion.button)"

    def test_linkedin_page_has_form_labels(self):
        """Página LinkedIn deve ter labels ou aria-labels nos inputs."""
        content = read_file(_LINKEDIN)
        has_label = bool(re.search(r'<label|aria-label', content, re.IGNORECASE))
        assert has_label, "Página LinkedIn deve ter labels ou aria-labels nos inputs"

    def test_linkedin_textarea_has_placeholder(self):
        """Textarea deve ter placeholder descritivo."""
        content = read_file(_LINKEDIN)
        has_placeholder = bool(re.search(r'placeholder', content, re.IGNORECASE))
        assert has_placeholder, "Textarea de análise deve ter placeholder descritivo"

    def test_no_inline_onclick_without_jsx_handler(self):
        """Boa prática: evitar onclick inline, usar onClick JSX."""
        content = read_file(_LINKEDIN)
        has_inline_onclick = bool(re.search(r'\sonclick=\s*["\']', content))
        assert not has_inline_onclick, "Evitar onclick inline — usar onClick do React"

    def test_buttons_have_accessibility_text(self):
        """Botões devem ter texto visível ou aria-label (WCAG 4.1.2).

        A checagem é por botão: o bloco entre <button> e </button> precisa de
        caracteres visíveis (não tags, não expressão JSX) OU um aria-label na
        tag de abertura. Botão de ícone puro sem aria-label é violação —
        antes isso era pytest.skip (marcador macio que escondia o defeito).
        """
        content = read_file(_LAYOUT_COMP)
        blocos = re.findall(r"<button\b[^>]*>.*?</button>", content, re.DOTALL)
        violacoes = []
        for bloco in blocos:
            fim_tag = bloco.index(">")
            abri = bloco[: fim_tag + 1]
            corpo = bloco[fim_tag + 1 : -len("</button>")]
            tem_aria = "aria-label" in abri
            # tira tags aninhadas e a expressão JSX inteira → sobra só texto
            sem_tags = re.sub(r"<[^>]*>", " ", corpo)
            sem_expressao = re.sub(r"\{[^}]*\}", " ", sem_tags)
            tem_texto = bool(re.search(r"[^ ]", sem_expressao.strip()))
            if not (tem_aria or tem_texto):
                violacoes.append(abri.strip()[:80])
        assert not violacoes, \
            "Botão sem texto acessível (adicione aria-label): " + " | ".join(violacoes)


# ============================================================================
# Keyboard navigation (static analysis of tab order)
# ============================================================================

class TestKeyboardNavigation:
    def test_tabs_no_hidden_focus_traps(self):
        """Tab index negativo deve ser usado com moderação."""
        content = read_file(_LINKEDIN)
        hidden_focus = re.findall(r'tabIndex=\{-1\}', content)
        assert len(hidden_focus) <= 2, \
            f"Muitos elementos com tabIndex={{-1}} ({len(hidden_focus)}) — pode quebrar navegação por teclado"

    def test_forms_have_submit_mechanism(self):
        """Página LinkedIn deve ter mecanismo de submit (button, form, ou onClick)."""
        content = read_file(_LINKEDIN)
        # Botão com onClick ou type=submit ou form com onSubmit conta como submit
        has_submit = bool(re.search(r'onClick=|type\s*=\s*(?:["\x27])submit(?:["\x27])|onSubmit', content, re.IGNORECASE))
        assert has_submit, "Formulário de análise LinkedIn deve ter mechanismo de submit"


# ============================================================================
# Color contrast heuristic (light text on dark bg)
# ============================================================================

class TestColorContrast:
    """Verifica se há classes de cor legíveis em fundo escuro."""

    def test_dark_mode_text_contrast(self):
        light_text_classes = [
            "text-white", "text-slate-100", "text-slate-200", "text-slate-300",
            "text-blue-200", "text-cyan-200", "text-indigo-200", "text-green-200",
            "text-gray-100", "text-gray-200", "text-gray-300",
        ]
        content = read_file(_LINKEDIN)
        light_count = sum(content.count(cls) for cls in light_text_classes)
        assert light_count >= 5, \
            f"Muito poucas classes de texto claro ({light_count}) — verifique contraste em fundo escuro"

    def test_no_white_on_white(self):
        """Nenhuma classe de texto escuro em fundo branco (problema raro, mas válido)."""
        # Verifica se há combinações perigosas
        content = read_file(_LINKEDIN)
        # No tema dark do app, texto escuro (text-slate-900) seria problema
        dark_text = re.findall(r'text-slate-900|text-gray-900|text-black', content)
        assert len(dark_text) == 0, \
            f"Texto escuro ({dark_text}) em fundo escuro — invisível. Use text-slate-300 ou superior."

"""Smart mode: connect an AI and describe the ideal customer it scores leads against."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMenu, QSpinBox, QVBoxLayout, QWidget

from app.core import ai, credentials, db
from app.core import search as searches
from app.i18n import t
from app.ui.pages.base import Page
from app.ui.widgets.common import (ChoiceButtons, FormRow, Section, clear_layout, danger_button,
                                   ghost_button, hint, muted, open_url, primary_button, row,
                                   secondary_button, small_button, wrap_row)
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.inputs import checkbox, combo, get_text, line_edit, password_edit, set_text, \
    text_box
from app.workers.base import Task

TRY_LEADS = 5  # leads "Try it on my leads" scores
# The extra columns the AI can fill: setting -> label
EXTRA_LABELS = {
    "ai_opener": "Write an opening line for a cold email or call",
    "ai_needs": "Say what each business seems to need (for your pitch)",
    "ai_channel": "Pick the best way to reach each business",
}


def number(low: int, high: int, value: int, special: str) -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    box.setSpecialValueText(t(special))
    box.setFixedWidth(130)
    return box

PROFILE_EXAMPLE = ("For example: independent dental clinics (not hospital chains) with a website "
                   "but little social media, rated under 4.5 stars, that might want help "
                   "getting more patients online.")


class SmartPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Smart mode",
                        "Connect an AI and describe your ideal customer. While a search runs, the "
                        "AI checks every business is genuine and scores how well it fits, with a "
                        "one-line reason. You bring the AI, so GeoHarvest stays free.")
        body = self.scroll_body()
        layout = body.body_layout
        saved = db.get_setting("ai_provider", "")

        # --- 1. which AI ----------------------------------------------------
        choose = Section("1. Choose your AI",
                         "Free choices first. 'On this PC' runs entirely on your computer: free, "
                         "private, and fast if you have a strong graphics card.")
        self.provider = ChoiceButtons([(p.key, p.name) for p in ai.PROVIDERS],
                                      saved or "gemini", on_change=self._provider_changed)
        choose.add(self.provider)
        self.note = muted("")
        self.key_link = ghost_button("Get a key", lambda: open_url(self._current().key_url))
        choose.add(row(self.note, self.key_link, stretch=0))

        self.key_row = FormRow("Key", "Stored encrypted on this computer, readable only by your "
                                      "Windows account. Sent only to the provider you picked.")
        self.key = password_edit("Paste your key here")
        self.show_key = secondary_button("Show", self._toggle_key)
        self.key_row.add(row(self.key, self.show_key, stretch=0))
        choose.add(self.key_row)

        self.url_row = FormRow("Address", "Where the AI service is listening.")
        self.base_url = line_edit("http://localhost:11434/v1")
        self.url_row.add(self.base_url)
        choose.add(self.url_row)

        model_row = FormRow("Model", "Press 'Load models' to see what your key can use.")
        self.model = combo([], translate=False)
        self.model.setEditable(True)
        self.model.setMinimumWidth(380)
        self.load_button = secondary_button("Load models", self.load_models)
        model_row.add(row(self.model, self.load_button, None))
        choose.add(model_row)
        layout.addWidget(choose)

        # --- 2. ideal customer ----------------------------------------------
        profile = Section("2. Describe your ideal customer",
                          "Plain words are fine. The more specific you are, the better the scores. "
                          "What you are selling, who buys it, and who is not worth contacting.")
        self.profiles_holder = QWidget()
        self.profiles_holder.setProperty("role", "plain")
        QVBoxLayout(self.profiles_holder).setContentsMargins(0, 0, 0, 0)
        profile.add(self.profiles_holder)
        self.profile = text_box(PROFILE_EXAMPLE, lines=5)
        set_text(self.profile, db.get_setting("ai_profile", ""))
        profile.add(self.profile)
        never = FormRow("Never a fit", "The AI scores these 0, so 'Leave out leads the AI scores "
                                       "below' leaves them out.")
        self.dealbreakers = text_box("For example: chains and franchises, government offices, "
                                     "hospitals", lines=2)
        set_text(self.dealbreakers, db.get_setting("ai_dealbreakers", ""))
        never.add(self.dealbreakers)
        profile.add(never)
        layout.addWidget(profile)
        self._fill_profiles()

        # --- 3. low scores --------------------------------------------------
        low = Section("3. Leads that do not fit")
        min_score = int(db.get_setting("ai_min_score", 0) or 0)
        self.drop_low = checkbox("Leave out leads the AI scores below", bool(min_score))
        self.min_score = QSpinBox()
        self.min_score.setRange(1, 100)
        self.min_score.setValue(min_score or 50)
        self.min_score.setFixedWidth(90)
        low.add(row(self.drop_low, self.min_score, None))
        low.add(hint("Scores: 80 and up is a good fit (Hot), 50 to 79 maybe (Warm), below 50 a "
                     "poor fit (Cold). Leave this off to keep every lead and sort by AI score on "
                     "the Leads page."))
        layout.addWidget(low)

        # --- 4. what the AI adds --------------------------------------------
        extras = Section("4. What the AI adds",
                         "Each one is a column on the Leads page and in exports. The AI writes "
                         "in the language GeoHarvest is set to.")
        self.extras = {key: checkbox(label, bool(db.get_setting(key, False)))
                       for key, label in EXTRA_LABELS.items()}
        for box in self.extras.values():
            extras.add(box)
        self.read_site = checkbox("Let the AI read the start of each business's website",
                                  bool(db.get_setting("ai_read_site", False)))
        extras.add(self.read_site)
        extras.add(hint("Better scores and opening lines, but each lead uses more of your key's "
                        "allowance. Needs 'Visit each website' on the New search page."))
        layout.addWidget(extras)

        # --- 5. limits ------------------------------------------------------
        limits = Section("5. Limits",
                         "Keep a paid key's cost down, and stay inside a free key's limits.")
        self.max_leads = number(0, 100000, int(db.get_setting("ai_max_leads", 0) or 0),
                                "Every lead")
        limits.add(row(muted("AI checks at most", wrap=False), self.max_leads,
                       muted("leads per search", wrap=False), None))
        self.per_minute = number(0, 1000, int(db.get_setting("ai_per_minute", 0) or 0),
                                 "No limit")
        limits.add(row(muted("At most", wrap=False), self.per_minute,
                       muted("requests a minute", wrap=False), None))
        limits.add(hint("Free Gemini keys allow about 10 to 15 requests a minute. Each request "
                        "checks up to 8 leads."))
        self.contact_only = checkbox("Only check leads with a phone number or an email",
                                     bool(db.get_setting("ai_contact_only", False)))
        limits.add(self.contact_only)
        layout.addWidget(limits)
        layout.addStretch(1)

        self.status = muted("", wrap=True)
        self.root.addWidget(self.status)
        self.save_button = primary_button("Save and test", self.save_and_test)
        self.off_button = danger_button("Turn Smart mode off", self.turn_off)
        self.try_button = secondary_button("Try it on my leads", self.try_on_leads)
        self.try_button.setToolTip(t("Save, then score {count} of your newest leads to see how "
                                     "your description works", count=TRY_LEADS))
        self.root.addWidget(row(None, self.off_button, self.try_button, self.save_button))

        self._provider_changed(self.provider.get())
        self._show_state()

    # --- form ---------------------------------------------------------------
    def _current(self) -> ai.Provider:
        return ai.BY_KEY[self.provider.get()]

    def _provider_changed(self, key: str) -> None:
        provider = ai.BY_KEY[key]
        self.note.setText(provider.note)
        self.key_link.setVisible(bool(provider.key_url))
        self.key_link.setText(t("Get a free key") if "Free" in provider.note and provider.needs_key
                              else "Get a key" if provider.needs_key else "Download")
        self.key_row.setVisible(provider.kind != "openai" or provider.needs_key
                                or key == "custom")
        self.key.setText(credentials.load_secret(credentials.ai_key_name(key)))
        local = not provider.needs_key
        self.url_row.setVisible(local)
        same = key == db.get_setting("ai_provider", "")
        self.base_url.setText((db.get_setting("ai_base_url", "") if same else "")
                              or provider.base_url)
        self.model.clear()
        self.model.lineEdit().setText((db.get_setting("ai_model", "") if same else "")
                                      or provider.model)

    def _toggle_key(self) -> None:
        hidden = self.key.echoMode() == QLineEdit.EchoMode.Password
        self.key.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.show_key.setText(t("Hide") if hidden else t("Show"))

    def _form_config(self) -> dict:
        provider = self._current()
        return {
            "provider": provider.key, "kind": provider.kind,
            "base_url": (self.base_url.text().strip() if self.url_row.isVisible()
                         else provider.base_url).rstrip("/"),
            "model": self.model.lineEdit().text().strip(),
            "key": self.key.text().strip(),
            "profile": get_text(self.profile),
            "min_score": self.min_score.value() if self.drop_low.isChecked() else 0,
        }

    def _show_state(self) -> None:
        cfg = ai.settings()
        self.off_button.setEnabled(cfg is not None)
        if cfg is None:
            self.status.setText(t("Smart mode is off. Set it up above, then press Save and test."))
        else:
            self.status.setText(t("Smart mode is on: {name}, model {model}. Switch on 'Smart "
                                  "mode' on the New search page to use it.",
                                  name=ai.BY_KEY[cfg['provider']].name, model=cfg['model']))

    # --- actions ------------------------------------------------------------
    def load_models(self) -> None:
        cfg = self._form_config()
        self.load_button.setEnabled(False)
        self.load_button.setText(t("Loading..."))

        def done(models: list) -> None:
            typed = self.model.lineEdit().text()
            self.model.clear()
            self.model.addItems(models)
            self.model.lineEdit().setText(typed if typed in models or not models else models[0])
            self.notify(t("{count} models available.", count=len(models)) if models else
                        "No models found. Is a model downloaded and loaded?",
                        "success" if models else "warn")

        def finish() -> None:
            self.load_button.setEnabled(True)
            self.load_button.setText(t("Load models"))

        Task(ai.list_models, cfg).start(on_result=self.guard(done),
                                        on_error=self.guard(lambda m: self.notify(m, "error", 8000)),
                                        on_done=self.guard(finish))

    def save(self) -> dict:
        cfg = self._form_config()
        credentials.save_secret(credentials.ai_key_name(cfg["provider"]), cfg["key"])
        db.set_setting("ai_provider", cfg["provider"])
        db.set_setting("ai_model", cfg["model"])
        db.set_setting("ai_base_url", cfg["base_url"] if self.url_row.isVisible() else "")
        db.set_setting("ai_profile", cfg["profile"])
        db.set_setting("ai_min_score", cfg["min_score"])
        db.set_setting("ai_dealbreakers", get_text(self.dealbreakers))
        for key, box in self.extras.items():
            db.set_setting(key, box.isChecked())
        db.set_setting("ai_read_site", self.read_site.isChecked())
        db.set_setting("ai_max_leads", self.max_leads.value())
        db.set_setting("ai_per_minute", self.per_minute.value())
        db.set_setting("ai_contact_only", self.contact_only.isChecked())
        self._show_state()
        self.window_.refresh_status()
        return cfg

    def save_and_test(self) -> None:
        cfg = self.save()
        self.save_button.setEnabled(False)
        self.status.setText(t("Testing: asking the AI to score a sample business..."))

        def done(result: dict) -> None:
            self.status.setText(t("Working. The AI scored a sample dental clinic {ai_score} "
                                  "({ai_verdict}): {ai_reason}",
                                  ai_score=result['ai_score'], ai_verdict=result['ai_verdict'],
                                  ai_reason=result['ai_reason']))
            self.notify("Smart mode is working.", "success")

        def failed(message: str) -> None:
            self.status.setText(t("Saved, but the test failed: {message}", message=message))
            self.notify(message, "error", 8000)

        Task(ai.test, cfg).start(on_result=self.guard(done), on_error=self.guard(failed),
                                 on_done=self.guard(lambda: self.save_button.setEnabled(True)))

    def try_on_leads(self) -> None:
        """Score a few of the newest leads with everything as set here, to tune the
        description before a big search."""
        leads = searches.all_leads()[-TRY_LEADS:][::-1]
        if not leads:
            self.notify("Run a search first: there are no leads to try it on yet.", "warn")
            return
        self.save()
        cfg = ai.settings()
        self.try_button.setEnabled(False)
        self.status.setText(t("Trying it on {count} of your leads...", count=len(leads)))
        searched_for = ", ".join(dict.fromkeys(lead.get("category") or "business"
                                               for lead in leads))

        def done(scored: dict) -> None:
            lines = []
            for lead in leads:
                fields = scored.get(lead["place_id"])
                if fields:
                    lines.append(t("{name}: {ai_score} ({ai_tag}), {ai_reason}",
                                   name=lead.get("name", ""), ai_score=fields["ai_score"],
                                   ai_tag=fields["ai_tag"], ai_reason=fields["ai_reason"]))
            self.status.setText("\n".join(lines) or t("The AI answered, but not with scores. "
                                                       "Try a different model."))

        def failed(message: str) -> None:
            self.status.setText(t("The try failed: {message}", message=message))
            self.notify(message, "error", 8000)

        Task(ai.score, cfg, searched_for, leads).start(
            on_result=self.guard(done), on_error=self.guard(failed),
            on_done=self.guard(lambda: self.try_button.setEnabled(True)))

    # --- saved descriptions ---------------------------------------------------
    def _fill_profiles(self) -> None:
        layout = self.profiles_holder.layout()
        clear_layout(layout)
        buttons = []
        for name in ai.profiles():
            button = small_button(name, lambda _c=False, n=name: self._use_profile(n))
            button.setToolTip(t("Your saved description. Right-click to delete it."))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda _pos, n=name, b=button: self._profile_menu(n, b))
            buttons.append(button)
        examples = small_button("Fill in an example")
        menu = QMenu(examples)
        for name, text in ai.EXAMPLES:
            menu.addAction(t(name), lambda x=text: self._fill_example(x))
        examples.setMenu(menu)
        save = small_button("Save this description...", self._save_profile)
        save.setToolTip(t("Keep this description and the 'Never a fit' list, to switch "
                          "between them with one click"))
        layout.addWidget(wrap_row(*buttons, examples, save))

    def _fill_example(self, text: str) -> None:
        set_text(self.profile, t(text))

    def _use_profile(self, name: str) -> None:
        saved = ai.profiles().get(name)
        if saved is None:
            return
        set_text(self.profile, saved["profile"])
        set_text(self.dealbreakers, saved["never"])
        self.notify(t("Using your description {name}. Press Save and test to keep it.",
                      name=name), "success")

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(self, t("Save this description"),
                                        t("A name for this ideal customer, like 'Dentists for "
                                          "SEO'."))
        name = " ".join(name.split())[:40]
        if not ok or not name:
            return
        if name in ai.profiles() and not ConfirmDialog.ask(
                self, "Replace the description?",
                t("You already have a description called {name}. Replace it?", name=name),
                "Replace"):
            return
        ai.save_profile(name, get_text(self.profile), get_text(self.dealbreakers))
        self._fill_profiles()
        self.notify(t("Saved the description {name}.", name=name), "success")

    def _profile_menu(self, name: str, button) -> None:
        menu = QMenu(self)
        menu.addAction(t("Use it"), lambda: self._use_profile(name))
        menu.addAction(t("Delete this description"), lambda: self._delete_profile(name))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _delete_profile(self, name: str) -> None:
        if ConfirmDialog.ask(self, "Delete this description?", t("Delete {name}?", name=name),
                             "Delete", danger=True):
            ai.delete_profile(name)
            self._fill_profiles()

    def turn_off(self) -> None:
        db.set_setting("ai_provider", "")
        self._show_state()
        self.window_.refresh_status()
        self.notify("Smart mode is off. Your key stays saved in case you turn it back on.")

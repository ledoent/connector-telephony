/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {Store} from "@mail/../tests/mock_server/store";
import {fields} from "@web/../tests/web_test_helpers";
import {mailModels} from "@mail/../tests/mail_test_helpers";

export class MailActivity extends mailModels.MailActivity {
    main_partner_id = fields.Many2one({
        relation: "res.partner",
        string: "Main Partner",
    });
    main_partner = fields.Char();
    get_call_activities() {
        const items = this.search([["activity_category", "=", "phonecall"]]);
        return new Store().add(this.browse(items), "_store_activity_fields").as_dict();
    }

    _store_activity_fields(res) {
        super._store_activity_fields(res);
        res.one("main_partner_id", []);
        res.attr("main_partner");
    }
}

import {RUN_STATES,ARCHIVE_STATES} from '../../constants/enums.js';
import {esc} from '../../utils/html.js';
const LABELS={...RUN_STATES,...ARCHIVE_STATES};
export const badge=value=>`<span class="badge ${esc(value)}">${esc(LABELS[value]||value)}</span>`;

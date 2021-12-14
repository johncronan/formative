import {MDCRipple} from '@material/ripple/index';
import {MDCTextField} from '@material/textfield';
import {MDCNotchedOutline} from '@material/notched-outline';

const texts = [];
document.querySelectorAll('.mdc-text-field')
        .forEach(text => texts.push(new MDCTextField(text)));
const outlines = [];
document.querySelectorAll('.mdc-notched-outline')
        .forEach(outline => outlines.push(new MDCNotchedOutline(outline)));

window.addEventListener("pageshow", function() {
  texts.forEach(text => { if (text.value) text.value = text.value; });
});

import {MDCRipple} from '@material/ripple/index';
import {MDCFormField} from '@material/form-field';
import {MDCTextField} from '@material/textfield';
import {MDCNotchedOutline} from '@material/notched-outline';
import {MDCRadio} from '@material/radio';

const texts = [];
document.querySelectorAll('.mdc-text-field')
        .forEach(text => texts.push(new MDCTextField(text)));
const outlines = [];
document.querySelectorAll('.mdc-notched-outline')
        .forEach(outline => outlines.push(new MDCNotchedOutline(outline)));
const radios = [];
document.querySelectorAll('.mdc-radio')
        .forEach(radio => radios.push(new MDCRadio(radio)));
const formFields = [];
//document.querySelectorAll('.mdc-form-field')
//        .forEach(field => formFields.push(new MDCFormField('.mdc-form-field')))

// TODO: set formField.input = radio

window.addEventListener("pageshow", function() {
  texts.forEach(text => { if (text.value) text.value = text.value; });
});

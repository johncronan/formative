import {MDCRipple} from '@material/ripple/index';
import {MDCFormField} from '@material/form-field';
import {MDCTextField} from '@material/textfield';
import {MDCTextFieldCharacterCounter}
    from '@material/textfield/character-counter';
import {MDCNotchedOutline} from '@material/notched-outline';
import {MDCRadio} from '@material/radio';
import {MDCCheckbox} from '@material/checkbox';

import axios from 'axios';
axios.defaults.xsrfHeaderName = "X-CSRFToken";

const texts = [];
document.querySelectorAll('.mdc-text-field')
        .forEach(text => {
           var t = new MDCTextField(text);
           texts.push(t);
           if (text.classList.contains('rp-text-field--invalid')) {
               t.useNativeValidation = false;
               t.valid = false;
           }
        });

const counters = [];
document.querySelectorAll('.mdc-text-field-character-counter')
        .forEach(c => counters.push(new MDCTextFieldCharacterCounter(c)));

const outlines = [];
document.querySelectorAll('.mdc-notched-outline')
        .forEach(outline => outlines.push(new MDCNotchedOutline(outline)));

const radios = [];
document.querySelectorAll('.mdc-radio')
        .forEach(radio => radios.push(new MDCRadio(radio)));

const checkboxes = [];
document.querySelectorAll('.mdc-checkbox')
        .forEach(checkbox => checkboxes.push(new MDCCheckbox(checkbox)));

const formFields = [];
//document.querySelectorAll('.mdc-form-field')
//        .forEach(field => formFields.push(new MDCFormField('.mdc-form-field')))

// TODO: set formField.input = radio, for ripple?

const ripples = [];
document.querySelectorAll('.mdc-button,.mdc-button-icon')
        .forEach(button => ripples.push(new MDCRipple(button)));

window.addEventListener("pageshow", function() {
  document.querySelectorAll('.rp-text-field--invalid')
          .forEach(text => text.classList.add('mdc-text-field--invalid'));
  
  texts.forEach(text => { if (text.value) text.value = text.value; });
});

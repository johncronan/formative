import {MDCRipple} from '@material/ripple/index';
import {MDCFormField} from '@material/form-field';
import {MDCTextField} from '@material/textfield';
import {MDCTextFieldCharacterCounter}
    from '@material/textfield/character-counter';
import {MDCNotchedOutline} from '@material/notched-outline';
import {MDCRadio} from '@material/radio';
import {MDCCheckbox} from '@material/checkbox';
import {MDCDataTable} from '@material/data-table';

import Sortable from 'sortablejs';

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
//       .forEach(field => formFields.push(new MDCFormField('.mdc-form-field')))

// TODO: set formField.input = radio, for ripple?

//const dataTables = [];
//document.querySelectorAll('.mdc-data-table')
//        .forEach(table => dataTables.push(new MDCDataTable(table)));

const ripples = [];
document.querySelectorAll('.mdc-button,.mdc-button-icon')
        .forEach(button => ripples.push(new MDCRipple(button)));

function itemMove(rowEl, rank) {
  var itemId = rowEl.dataset.id;
  var href = document.location.href;
  var url = href.substring(0, href.lastIndexOf('/'));
  
  var data = new FormData();
  data.append('item_id', itemId);
  data.append('rank', rank);
  axios.post(url + '/moveitem', data)
    .then(res => {
    }).catch(err => {
    });
}

document.addEventListener('dragover', function(e) { e.preventDefault() });

document.querySelectorAll('.rp-collection-table-body')
        .forEach(tbody => Sortable.create(tbody, {
          handle: '.rp-sort-handle-cell',
          animation: 120,
          onEnd: event => {
            var itemRow = event.item;
            if (event.oldIndex != event.newIndex)
                itemMove(itemRow, event.newIndex + 1);
          }
        }));

function uploadFile() {
  var config = {
    onUploadProgress: event => {
      var percentCompleted = Math.round((event.loaded * 100) / event.total);
      
    }
  };
}

function newItems(blockId, files, itemId) {
  var href = document.location.href;
  var url = href.substring(0, href.lastIndexOf('/'));
  
  var data = new FormData();
  data.append('block_id', blockId);
  if (itemId) data.append('item_id', itemId);
  
  if (files) for (let i=0; i < files.length; i++) {
    data.append('filesize' + files[i].size, files[i].name);
  }
  
  axios.post(url + '/item', data)
    .then(res => {
      var table = document.querySelector('#collection' + blockId);
      var tablediv = table.parentElement.parentElement;
      var tbody = table.firstElementChild;
      if (itemId) {
        var itemEl = tbody.querySelector('tr[data-id="' + itemId + '"]');
        itemEl.innerHTML = res.data.trim();
        // if no error, call the upload func
      } else {
        var tablePos = tbody.querySelector('tr:last-child');
        var html = res.data.trim();
        if (!tablePos) {
          tbody.innerHTML = html;
          tablediv.style.display = 'flex';
        } else tablePos.insertAdjacentHTML('afterend', html);
        var numRows = tbody.children.length;
        var maxItems = table.dataset.maxItems;
        var sel = '.rp-collection-button[data-block-id="' + blockId + '"]';
        if (numRows >= maxItems) document.querySelector(sel).disabled = true;
        //  if there's a file (and no error), call the upload func
      }
      document.querySelectorAll('.rp-item-upload')
              .forEach(button => button.onclick = uploadClick);
      document.querySelectorAll('.rp-item-remove')
              .forEach(button => button.onclick = removeClick);
    })
    .catch(err => {
      
    });
  
}

function filesSelected(event, blockId, itemId) {
  var fileInput = event.target;
  newItems(blockId, fileInput.files, itemId);
  fileInput.value = '';
}

function collectionClick(event) {
  var buttonEl = event.target.parentElement;
  var blockId = buttonEl.dataset.blockId;
  
  if (buttonEl.dataset.needsFile) {
    var fileInput = document.querySelector('input[name="file' + blockId + '"]');
    fileInput.onchange = event => filesSelected(event, blockId);
    fileInput.click();
  } else {
    newItems(blockId);
  }
}

document.querySelectorAll('.rp-collection-button')
        .forEach(button => button.onclick = collectionClick);

function uploadClick(event) {
  var rowEl = event.target.parentElement.parentElement;
  var blockId = rowEl.dataset.blockId;
  var id = rowEl.dataset.id;
  var fileInput = document.querySelector('input[name="itemfile' + id + '"]');
  fileInput.onchange = event => filesSelected(event, blockId, id);
  fileInput.click();
}

document.querySelectorAll('.rp-item-upload')
        .forEach(button => button.onclick = uploadClick);

function removeClick(event) {
  var href = document.location.href;
  var url = href.substring(0, href.lastIndexOf('/'));
  var rowEl = event.target.parentElement.parentElement;
  var blockId = rowEl.dataset.blockId;
  var id = rowEl.dataset.id;
  
  var data = new FormData();
  data.append('item_id', id);
  axios.post(url + '/removeitem', data)
    .then(res => {
      var tbody = rowEl.parentElement;
      tbody.removeChild(rowEl);
      var numRows = tbody.children.length;
      var table = tbody.parentElement;
      if (!numRows) {
        var tablediv = table.parentElement.parentElement;
        tablediv.style.display = 'none';
      }
      var maxItems = table.dataset.maxItems;
      if (numRows < maxItems) {
        var sel = '.rp-collection-button[data-block-id="' + blockId + '"]';
        document.querySelector(sel).disabled = false;
      }
    }).catch(err => {
    });
}

document.querySelectorAll('.rp-item-remove')
        .forEach(button => button.onclick = removeClick);

window.addEventListener("pageshow", function() {
  document.querySelectorAll('.rp-text-field--invalid')
          .forEach(text => text.classList.add('mdc-text-field--invalid'));
  
  texts.forEach(text => { if (text.value) text.value = text.value; });
});

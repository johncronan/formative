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
  var url = postUrlBase();
  
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

function postUrlBase() {
  var href = document.location.href;
  var url = href.substring(0, href.lastIndexOf('/'));
  return url;
}

function postFile(rowEl, file) {
  var itemId = rowEl.dataset.id
  var url = postUrlBase();
  var data = new FormData();
  data.append('item_id', itemId);
  data.append('file', file);
  
  var config = {
    onUploadProgress: event => {
      var percentCompleted = Math.round((event.loaded * 100) / event.total);
      console.log(percentCompleted);
    }
  };
  
  axios.post(url + '/file', data, config)
    .then(res => {
      setStatus(rowEl, 'normal');
    });
//    .catch(err => {
//      
//    });
}

var filesQueue = [];
var simultaneous = 4;

function processQueue() {
  for (let i=0; i < filesQueue.length; i++) {
    if (i >= simultaneous) break;
    if (!filesQueue[i][0]) {
      filesQueue[i][0] = true;
      postFile(filesQueue[i][1], filesQueue[i][2]);
    }
  }
}

function uploadFile(rowEl, file) {
  filesQueue.push([false, rowEl, file]);
}

function rowStatus(rowEl) {
  if (rowEl.querySelector('td.rp-item-progress-cell').style.display != 'none')
    return 'upload';
  if (rowEl.querySelector('td.rp-item-message-cell').style.display != 'none')
    return 'error';
  return 'normal';
}

function setStatus(rowEl, status) {
  var hide, show;
  if (status == 'normal') {
    hide = 'td.rp-item-progress-cell,td.rp-item-message-cell';
    show = 'td.rp-item-field-cell';
  } else if (status == 'error') {
    hide = 'td.rp-item-progress-cell,td.rp-item-field-cell';
    show = 'td.rp-item-message-cell';
  }
  rowEl.querySelectorAll(hide).forEach(row => row.style.display = 'none');
  rowEl.querySelectorAll(show).forEach(row => row.style.display = 'table-cell');
}

function newItems(blockId, files, itemId) {
  var url = postUrlBase();
  
  var data = new FormData();
  data.append('block_id', blockId);
  if (itemId) data.append('item_id', itemId);
  
  var haveFile;
  var filesArray = [];
  if (files) for (let i=0; i < files.length; i++) {
    data.append('filesize' + files[i].size, files[i].name);
    filesArray.push(files[i]);
    haveFile = true;
  }
  
  axios.post(url + '/item', data)
    .then(res => {
      var table = document.querySelector('#collection' + blockId);
      var tablediv = table.parentElement.parentElement;
      var tbody = table.firstElementChild;
      var rows = [];
      if (itemId) {
        var itemEl = tbody.querySelector('tr[data-id="' + itemId + '"]');
        itemEl.innerHTML = res.data.trim();
        rows = [itemEl];
      } else {
        var tablePos = tbody.querySelector('tr:last-child');
        var html = res.data.trim();
        if (!tablePos) {
          tbody.innerHTML = html;
          tablediv.style.display = 'flex';
          rows = tbody.querySelectorAll('tr');
        } else {
          tablePos.insertAdjacentHTML('afterend', html);
          let element = tablePos;
          while (element = element.nextElementSibling) {
            rows.push(element);
          }
        }
        var numRows = tbody.children.length;
        var maxItems = table.dataset.maxItems;
        var sel = '.rp-collection-button[data-block-id="' + blockId + '"]';
        if (numRows >= maxItems) document.querySelector(sel).disabled = true;
      }
      
      if (haveFile) for (let i=0; i < rows.length; i++) {
        if (rowStatus(rows[i]) == 'upload') uploadFile(rows[i], filesArray[i]);
      }
      processQueue();
      document.querySelectorAll('.rp-item-upload')
              .forEach(button => button.onclick = uploadClick);
      document.querySelectorAll('.rp-item-remove')
              .forEach(button => button.onclick = removeClick);
    });
//    .catch(err => {
//      
//    });
  
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
  var url = postUrlBase();
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

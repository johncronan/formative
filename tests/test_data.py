import pytest

from formative.models import Program, Form, FormBlock, CustomBlock, \
    CollectionBlock, FormLabel, FormDependency


# this is really just test-data creation, with a little testing on the side

@pytest.fixture(scope='session')
def program(db_no_rollback):
    p = Program(name='Co-Prosperity')
    p.save()
    yield p

def test_program(program):
    assert program

@pytest.fixture(scope='session')
def program_form(program):
    opt = { 'review_pre': 'Review your application below:' }
    f = Form(program=program, name='Exhibitions Application 2022', options=opt)
    f.save()
    yield f

def test_program_form(program_form):
    assert program_form

@pytest.fixture(scope='session')
def stock_name_block(program_form):
    b = FormBlock(form=program_form, name='name', options={'type': 'name'})
    b.save()
    yield b
    
def test_stock_block(stock_name_block):
    assert stock_name_block

@pytest.fixture(scope='session')
def stock_email_block(program_form, stock_name_block):
    b = FormBlock(form=program_form, name='contact', options={'type': 'email'})
    b.save()
    yield b

def test_stock_email_block(stock_email_block):
    assert stock_email_block

@pytest.fixture(scope='session')
def dependence_choice_block(program_form, stock_email_block):
    b = CustomBlock(form=program_form, name='choice',
                    type=CustomBlock.InputType.CHOICE,
                    options={'choices': ['foo', 'bar', 'baz', 'qux']})
    b.save()
    yield b

def test_dependence_choice_block(dependence_choice_block):
    assert dependence_choice_block
    
@pytest.fixture(scope='session')
def custom_text_block(program_form, dependence_choice_block):
    b = CustomBlock(form=program_form, name='answer', page=2,
                    type=CustomBlock.InputType.TEXT, max_chars=50)
    b.save()
    yield b

def test_custom_text_block(custom_text_block):
    assert custom_text_block

@pytest.fixture(scope='session')
def custom_textarea_block(program_form, stock_email_block, custom_text_block):
    b = CustomBlock(form=program_form, name='response', page=2,
                    type=CustomBlock.InputType.TEXT,
                    min_chars=1, max_chars=1000, num_lines=5, min_words=10,
                    dependence=stock_email_block)
    b.save()
    FormDependency(block=b, value='yes').save()
    yield b

def test_custom_textarea_block(custom_textarea_block):
    assert custom_textarea_block

@pytest.fixture(scope='session')
def collection_block_main(program_form, custom_textarea_block):
    b = CollectionBlock(form=program_form, name='files', page=2,
                        min_items=1, max_items=10, has_file=True,
                        name1='caption', name2='timecode',
                        options={'wide': ['caption'],
                                 'autoinit_filename': True})
    b.save()
    yield b

def test_collection_block_main(collection_block_main):
    collection = collection_block_main
    b = collection.form.blocks.get(page=0, name=collection.name1)
    
    assert b
    b.min_chars = 1
    b.save()
    

@pytest.fixture(scope='session')
def collection_block_optional(program_form, collection_block_main):
    b = CollectionBlock(form=program_form, name='files', page=2,
                        min_items=0, max_items=1, has_file=True)
    b.save()
    yield b

def test_collection_block_optional(collection_block_optional):
    assert collection_block_optional

@pytest.fixture(scope='session')
def custom_choice_block(program_form, dependence_choice_block,
                        collection_block_optional):
    b = CustomBlock(form=program_form, name='type', page=2,
                    type=CustomBlock.InputType.CHOICE, required=True,
                    options={'choices': ['foo', 'bar', 'baz']},
                    dependence=dependence_choice_block)
    b.save()
    FormDependency(block=b, value='foo').save()
    FormDependency(block=b, value='baz').save()
    yield b

def test_custom_choice_block(custom_choice_block):
    assert custom_choice_block

@pytest.fixture(scope='session')
def custom_numeric_block(program_form, dependence_choice_block,
                         custom_choice_block):
    b = CustomBlock(form=program_form, name='numitems', page=2,
                    type=CustomBlock.InputType.NUMERIC,
                    dependence=dependence_choice_block,
                    negate_dependencies=True)
    b.save()
    FormDependency(block=b, value='foo').save()
    FormDependency(block=b, value='qux').save()
    yield b

def test_custom_numeric_block(custom_numeric_block):
    assert custom_numeric_block

@pytest.fixture(scope='session')
def custom_boolean_block(program_form, custom_numeric_block):
    b = CustomBlock(form=program_form, name='optin', page=2,
                    type=CustomBlock.InputType.BOOLEAN)
    b.save()
    yield b

def test_custom_boolean_block(custom_boolean_block):
    assert custom_boolean_block

def test_publish_form(program_form, custom_boolean_block):
    program_form.publish()
    assert program_form.status == Form.Status.ENABLED

@pytest.fixture(scope='session')
def altered_labels(program_form, custom_numeric_block, custom_boolean_block):
    path = custom_boolean_block.name
    label1 = FormLabel.objects.get(form=program_form, path=path)

    label1.text = 'Sign up for our mailing list'
    label1.save()
    
    path = custom_numeric_block.name
    label2 = FormLabel.objects.get(form=program_form, path=path)
    
    label2.text = 'Number of items:'
    label2.save()
    
    yield [label1, label2]

def test_altered_labels(altered_labels):
    assert altered_labels

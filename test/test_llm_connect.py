import os
from unittest.mock import MagicMock, Mock, mock_open, patch
from biochatter.llm_connect import UnifiedConversation, HumanMessage, SystemMessage
from typing import Union
import openai
import pytest
from openai._exceptions import NotFoundError
from PIL import Image

from biochatter._image import (
    convert_and_resize_image,
    convert_to_pil_image,
    convert_to_png,
    encode_image,
    encode_image_from_url,
    process_image,
)
from biochatter.llm_connect import (
    AIMessage,
    AnthropicConversation,
    AzureGptConversation,
    GptConversation,
    HumanMessage,
    OllamaConversation,
    SystemMessage,
    WasmConversation,
    XinferenceConversation,
)


@pytest.fixture(scope="module", autouse=True)
def manage_test_context():
    import openai

    base_url = openai.base_url
    api_type = openai.api_type
    api_version = openai.api_version
    api_key = openai.api_key
    organization = openai.organization
    proxy = getattr(openai, "proxy", None)
    yield True

    openai.base_url = base_url
    openai.api_type = api_type
    openai.api_version = api_version
    openai.api_key = api_key
    openai.organization = organization
    if proxy is not None:
        openai.proxy = proxy
    elif hasattr(openai, "proxy"):
        delattr(openai, "proxy")


def test_empty_messages():
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )
    assert convo.get_msg_json() == "[]"


def test_single_message():
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )
    convo.messages.append(SystemMessage(content="Hello, world!"))
    assert convo.get_msg_json() == '[{"system": "Hello, world!"}]'


def test_multiple_messages():
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )
    convo.messages.append(SystemMessage(content="Hello, world!"))
    convo.messages.append(HumanMessage(content="How are you?"))
    convo.messages.append(AIMessage(content="I'm doing well, thanks!"))
    assert convo.get_msg_json() == (
        '[{"system": "Hello, world!"}, {"user": "How are you?"}, {"ai": "I\'m doing well, thanks!"}]'
    )


def test_unknown_message_type():
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )
    convo.messages.append(None)
    with pytest.raises(TypeError):
        convo.get_msg_json()


@patch("biochatter.llm_connect.openai.OpenAI")
def test_openai_catches_authentication_error(mock_openai):
    mock_openai.return_value.models.list.side_effect = openai._exceptions.AuthenticationError(
        (
            "Incorrect API key provided: fake_key. You can find your API key"
            " at https://platform.openai.com/account/api-keys."
        ),
        response=Mock(),
        body=None,
    )
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )

    success = convo.set_api_key(
        api_key="fake_key",
        user="test_user",
    )

    assert not success


@patch("biochatter.llm_connect.AzureChatOpenAI")
def test_azure_raises_request_error(mock_azure_chat):
    mock_azure_chat.side_effect = NotFoundError(
        message="Resource not found",
        response=Mock(),
        body=None,
    )

    convo = AzureGptConversation(
        model_name="gpt-35-turbo",
        deployment_name="test_deployment",
        prompts={},
        split_correction=False,
        version="2023-03-15-preview",
        base_url="https://api.openai.com",
    )

    with pytest.raises(NotFoundError):
        convo.set_api_key("fake_key")


@patch("biochatter.llm_connect.AzureChatOpenAI")
def test_azure(mock_azure_chat):
    """Test OpenAI Azure endpoint functionality.

    Azure connectivity is enabled by setting the corresponding environment
    variables.
    """
    convo = AzureGptConversation(
        model_name=os.getenv("AZURE_TEST_OPENAI_MODEL_NAME"),
        deployment_name=os.getenv("AZURE_TEST_OPENAI_DEPLOYMENT_NAME"),
        prompts={},
        split_correction=False,
        version=os.getenv("AZURE_TEST_OPENAI_API_VERSION"),
        base_url=os.getenv("AZURE_TEST_OPENAI_API_BASE"),
    )

    mock_azure_chat.return_value = Mock()

    assert convo.set_api_key(os.getenv("AZURE_TEST_OPENAI_API_KEY"))


xinference_models = {
    "48c76b62-904c-11ee-a3d2-0242acac0302": {
        "model_type": "embedding",
        "address": "",
        "accelerators": ["0"],
        "model_name": "gte-large",
        "dimensions": 1024,
        "max_tokens": 512,
        "language": ["en"],
        "model_revision": "",
    },
    "a823319a-88bd-11ee-8c78-0242acac0302": {
        "model_type": "LLM",
        "address": "0.0.0.0:46237",
        "accelerators": ["0"],
        "model_name": "llama2-13b-chat-hf",
        "model_lang": ["en"],
        "model_ability": ["embed", "generate", "chat"],
        "model_format": "pytorch",
        "context_length": 4096,
    },
}


@pytest.mark.skip(reason="Live test for development purposes")
def test_anthropic():
    conv = AnthropicConversation(
        model_name="claude-3-5-sonnet-20240620",
        prompts={},
        split_correction=False,
    )
    assert conv.set_api_key(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        user="test_user",
    )


def test_xinference_init():
    """Test generic LLM connectivity via the Xinference client. Currently depends
    on a test server.
    """
    base_url = os.getenv("XINFERENCE_BASE_URL", "http://localhost:9997")
    with patch("xinference.client.Client") as mock_client:
        mock_client.return_value.list_models.return_value = xinference_models
        convo = XinferenceConversation(
            base_url=base_url,
            prompts={},
            split_correction=False,
        )
        assert convo.set_api_key()


def test_xinference_chatting():
    base_url = os.getenv("XINFERENCE_BASE_URL", "http://localhost:9997")
    with patch("xinference.client.Client") as mock_client:
        response = {
            "id": "1",
            "object": "chat.completion",
            "created": 123,
            "model": "foo",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": " Hello there, can you sing me a song?",
                    },
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": 93,
                "completion_tokens": 54,
                "total_tokens": 147,
            },
        }
        mock_client.return_value.list_models.return_value = xinference_models
        mock_client.return_value.get_model.return_value.chat.return_value = response
        convo = XinferenceConversation(
            base_url=base_url,
            prompts={},
            correct=False,
        )
        (msg, token_usage, correction) = convo.query("Hello, world!")
        assert token_usage["completion_tokens"] > 0


def test_ollama_chatting():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    with patch("biochatter.llm_connect.ChatOllama") as mock_model:
        response = AIMessage(
            content="Hello there! It's great to meet you!",
            additional_kwargs={},
            response_metadata={
                "model": "llama3",
                "created_at": "2024-06-20T17:19:45.376245476Z",
                "message": {"role": "assistant", "content": ""},
                "done_reason": "stop",
                "done": True,
                "total_duration": 256049685,
                "load_duration": 3096978,
                "prompt_eval_duration": 15784000,
                "eval_count": 11,
                "eval_duration": 107658000,
            },
            type="ai",
            name=None,
            id="run-698c8654-13e6-4bbb-8d59-67e520f78eb3-0",
            example=False,
            tool_calls=[],
            invalid_tool_calls=[],
            usage_metadata=None,
        )

        mock_model.return_value.invoke.return_value = response

        convo = OllamaConversation(
            base_url=base_url,
            model_name="llama3",
            prompts={},
            correct=False,
        )
        (msg, token_usage, correction) = convo.query("Hello, world!")
        assert token_usage > 0


def test_wasm_conversation():
    # Initialize the class
    wasm_convo = WasmConversation(
        model_name="test_model",
        prompts={},
        correct=True,
        split_correction=False,
    )

    # Check if the model_name is correctly set
    assert wasm_convo.model_name == "test_model"

    # Check if the prompts are correctly set
    assert wasm_convo.prompts == {}

    # Check if the correct is correctly set
    assert wasm_convo.correct == True

    # Check if the split_correction is correctly set
    assert wasm_convo.split_correction == False

    # Test the query method
    test_query = "Hello, world!"
    result, _, _ = wasm_convo.query(test_query)
    assert result == test_query  # assuming the messages list is initially empty

    # Test the _primary_query method, add another message to the messages list
    wasm_convo.append_system_message("System message")
    result = wasm_convo._primary_query()
    assert result == test_query + "\nSystem message"


@pytest.fixture
def xinference_conversation():
    with patch("xinference.client.Client") as mock_client:
        # Mock the authentication check
        mock_client.return_value._check_cluster_authenticated.return_value = None
        mock_client.return_value.list_models.return_value = xinference_models
        mock_client.return_value.get_model.return_value.chat.return_value = (
            {"choices": [{"message": {"content": "Human message"}}]},
            {"completion_tokens": 0},
        )
        conversation = XinferenceConversation(
            base_url="http://localhost:9997",
            prompts={},
            correct=False,
        )
        return conversation


def test_single_system_message_before_human(xinference_conversation: XinferenceConversation):
    xinference_conversation.messages = [
        SystemMessage(content="System message"),
        HumanMessage(content="Human message"),
    ]
    history = xinference_conversation._create_history()
    assert history.pop() == {
        "role": "user",
        "content": "System message\nHuman message",
    }


def test_multiple_system_messages_before_human(xinference_conversation: XinferenceConversation):
    xinference_conversation.messages = [
        SystemMessage(content="System message 1"),
        SystemMessage(content="System message 2"),
        HumanMessage(content="Human message"),
    ]
    history = xinference_conversation._create_history()
    assert history.pop() == {
        "role": "user",
        "content": "System message 1\nSystem message 2\nHuman message",
    }


def test_multiple_messages_including_ai_before_system_and_human(
    xinference_conversation: XinferenceConversation,
):
    xinference_conversation.messages = [
        HumanMessage(content="Human message history"),
        AIMessage(content="AI message"),
        SystemMessage(content="System message"),
        HumanMessage(content="Human message"),
    ]
    history = xinference_conversation._create_history()
    assert history.pop() == {
        "role": "user",
        "content": "System message\nHuman message",
    }


def test_multiple_cycles_of_ai_and_human(xinference_conversation):
    xinference_conversation.messages = [
        HumanMessage(content="Human message history"),
        AIMessage(content="AI message"),
        HumanMessage(content="Human message"),
        AIMessage(content="AI message"),
        HumanMessage(content="Human message"),
        AIMessage(content="AI message"),
        SystemMessage(content="System message"),
        HumanMessage(content="Human message"),
    ]
    history = xinference_conversation._create_history()
    assert len(history) == 3
    assert history.pop() == {
        "role": "user",
        "content": "System message\nHuman message",
    }


def test_convert_and_resize_image():
    with Image.new("RGB", (2000, 2000)) as img:
        resized_img = convert_and_resize_image(img, max_size=1000)
        assert resized_img.size == (1000, 1000)


def test_convert_to_png():
    with Image.new("RGB", (100, 100)) as img:
        png_data = convert_to_png(img)
        assert isinstance(png_data, bytes)
        assert png_data.startswith(b"\x89PNG")


@patch("biochatter._image.pdf2image.convert_from_path")
def test_convert_to_pil_image_pdf(mock_convert_from_path):
    mock_convert_from_path.return_value = [Image.new("RGB", (1000, 1000))]
    with patch("biochatter._image.os.path.exists", return_value=True):
        with patch(
            "biochatter._image.os.path.abspath",
            side_effect=lambda x: x,
        ):
            img = convert_to_pil_image("test.pdf")
            assert isinstance(img, Image.Image)


@patch("biochatter._image.subprocess.run")
@patch("biochatter._image.os.path.exists", return_value=True)
@patch("biochatter._image.os.path.abspath", side_effect=lambda x: x)
def test_convert_to_pil_image_eps(mock_abspath, mock_exists, mock_run):
    with Image.new("RGB", (1000, 1000)) as img:
        with patch("biochatter._image.Image.open", return_value=img):
            converted_img = convert_to_pil_image("test.eps")
            assert isinstance(converted_img, Image.Image)


@patch("biochatter._image.Image.open")
@patch("biochatter._image.os.path.exists", return_value=True)
@patch("biochatter._image.os.path.abspath", side_effect=lambda x: x)
def test_convert_to_pil_image_unsupported(mock_abspath, mock_exists, mock_open):
    with pytest.raises(ValueError):
        convert_to_pil_image("test.txt")


def test_process_image():
    with patch("biochatter._image.convert_to_pil_image") as mock_convert:
        with Image.new("RGB", (100, 100)) as img:
            mock_convert.return_value = img
            encoded_image = process_image("test.jpg", max_size=1000)
            assert isinstance(encoded_image, str)
            assert encoded_image.startswith("iVBORw0KGgo")  # PNG base64 start


def test_encode_image():
    with Image.new("RGB", (100, 100)) as img:
        m = mock_open(read_data=img.tobytes())
        with patch("builtins.open", m):
            encoded_str = encode_image("test.jpg")
            assert isinstance(encoded_str, str)


def test_encode_image_from_url():
    with patch("biochatter.llm_connect.urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"image_data"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        mock_urlopen.return_value.info.return_value.get_content_type.return_value = "image/jpeg"

        with patch("tempfile.NamedTemporaryFile", new_callable=MagicMock) as mock_tempfile:
            mock_tempfile_instance = mock_tempfile.return_value.__enter__.return_value
            mock_tempfile_instance.name = "test_temp_file"

            write_mock = Mock()
            mock_tempfile_instance.write = write_mock

            with patch("biochatter._image.encode_image") as mock_encode:
                mock_encode.return_value = "base64string"

                with patch("os.remove") as mock_remove:
                    encoded_str = encode_image_from_url(
                        "http://example.com/image.jpg",
                    )

            write_mock.assert_called_once_with(b"image_data")
            mock_remove.assert_called_once_with("test_temp_file")
            assert isinstance(encoded_str, str)
            assert encoded_str == "base64string"


@pytest.mark.skip(reason="Live test for development purposes")
def test_append_local_image_gpt():
    convo = GptConversation(
        model_name="gpt-4o",
        prompts={},
        correct=False,
        split_correction=False,
    )
    convo.set_api_key(api_key=os.getenv("OPENAI_API_KEY"), user="test_user")

    convo.append_system_message(
        "You are an editorial assistant to a journal in biomedical science.",
    )

    convo.append_image_message(
        message=(
            "This text describes the attached image: "
            "Live confocal imaging of liver stage P. berghei expressing UIS4-mCherry and cytoplasmic GFP reveals different morphologies of the LS-TVN: elongated membrane clusters (left), vesicles in the host cell cytoplasm (center), and a thin tubule protruding from the PVM (right). Live imaging was performed 20?h after infection of hepatoma cells. Features are marked with white arrowheads."
        ),
        image_url="test/figure_panel.jpg",
        local=True,
    )

    result, _, _ = convo.query("Is the description accurate?")
    assert "yes" in result.lower()


@pytest.mark.skip(reason="Live test for development purposes")
def test_local_image_query_gpt():
    convo = GptConversation(
        model_name="gpt-4o",
        prompts={},
        correct=False,
        split_correction=False,
    )
    convo.set_api_key(api_key=os.getenv("OPENAI_API_KEY"), user="test_user")

    convo.append_system_message(
        "You are an editorial assistant to a journal in biomedical science.",
    )

    result, _, _ = convo.query(
        "Does this text describe the attached image: Live confocal imaging of liver stage P. berghei expressing UIS4-mCherry and cytoplasmic GFP reveals different morphologies of the LS-TVN: elongated membrane clusters (left), vesicles in the host cell cytoplasm (center), and a thin tubule protruding from the PVM (right). Live imaging was performed 20?h after infection of hepatoma cells. Features are marked with white arrowheads.",
        image_url="test/figure_panel.jpg",
    )
    assert "yes" in result.lower()


@pytest.mark.skip(reason="Live test for development purposes")
def test_append_online_image_gpt():
    convo = GptConversation(
        model_name="gpt-4o",
        prompts={},
        correct=False,
        split_correction=False,
    )
    convo.set_api_key(api_key=os.getenv("OPENAI_API_KEY"), user="test_user")

    convo.append_image_message(
        "This is a picture from the internet.",
        image_url="https://upload.wikimedia.org/wikipedia/commons/8/8f/The-Transformer-model-architecture.png",
    )

    result, _, _ = convo.query("What does this picture show?")
    assert "transformer" in result.lower()


@pytest.mark.skip(reason="Live test for development purposes")
def test_online_image_query_gpt():
    convo = GptConversation(
        model_name="gpt-4o",
        prompts={},
        correct=False,
        split_correction=False,
    )
    convo.set_api_key(api_key=os.getenv("OPENAI_API_KEY"), user="test_user")

    result, _, _ = convo.query(
        "What does this picture show?",
        image_url="https://upload.wikimedia.org/wikipedia/commons/8/8f/The-Transformer-model-architecture.png",
    )
    assert "transformer" in result.lower()


@pytest.mark.skip(reason="Live test for development purposes")
def test_local_image_query_xinference():
    url = "http://localhost:9997"
    convo = XinferenceConversation(
        base_url=url,
        prompts={},
        correct=False,
    )
    assert convo.set_api_key()

    result, _, _ = convo.query(
        "Does this text describe the attached image: Live confocal imaging of liver stage P. berghei expressing UIS4-mCherry and cytoplasmic GFP reveals different morphologies of the LS-TVN: elongated membrane clusters (left), vesicles in the host cell cytoplasm (center), and a thin tubule protruding from the PVM (right). Live imaging was performed 20?h after infection of hepatoma cells. Features are marked with white arrowheads.",
        image_url="test/figure_panel.jpg",
    )
    assert isinstance(result, str)


def test_chat_attribute_not_initialized():
    """Test that accessing chat before initialization raises AttributeError."""
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )

    with pytest.raises(AttributeError) as exc_info:
        _ = convo.chat

    assert "Chat attribute not initialized" in str(exc_info.value)
    assert "Did you call set_api_key()?" in str(exc_info.value)


def test_ca_chat_attribute_not_initialized():
    """Test that accessing ca_chat before initialization raises AttributeError."""
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )

    with pytest.raises(AttributeError) as exc_info:
        _ = convo.ca_chat

    assert "Correcting agent chat attribute not initialized" in str(exc_info.value)
    assert "Did you call set_api_key()?" in str(exc_info.value)


@patch("biochatter.llm_connect.openai.OpenAI")
def test_chat_attributes_reset_on_auth_error(mock_openai):
    """Test that chat attributes are reset to None on authentication error."""
    mock_openai.return_value.models.list.side_effect = openai._exceptions.AuthenticationError(
        "Invalid API key",
        response=Mock(),
        body=None,
    )

    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )

    # Set API key (which will fail)
    success = convo.set_api_key(api_key="fake_key")
    assert not success

    # Verify both chat attributes are None
    with pytest.raises(AttributeError):
        _ = convo.chat
    with pytest.raises(AttributeError):
        _ = convo.ca_chat


@pytest.mark.skip(reason="Test depends on langchain-openai implementation which needs to be updated")
@patch("biochatter.llm_connect.openai.OpenAI")
def test_chat_attributes_set_on_success(mock_openai):
    """Test that chat attributes are properly set when authentication succeeds.

    This test is skipped because it depends on the langchain-openai
    implementation which needs to be updated. Fails in CI with:
        __pydantic_self__ = ChatOpenAI()
            data = {'base_url': None, 'model_kwargs': {}, 'model_name': 'gpt-3.5-turbo', 'openai_api_key': 'fake_key', ...}
            values = {'async_client': None, 'cache': None, 'callback_manager': None, 'callbacks': None, ...}
            fields_set = {'model_kwargs', 'model_name', 'openai_api_base', 'openai_api_key', 'temperature'}
            validation_error = ValidationError(model='ChatOpenAI', errors=[{'loc': ('__root__',), 'msg': "AsyncClient.__init__() got an unexpected keyword argument 'proxies'", 'type': 'type_error'}])
                def __init__(__pydantic_self__, **data: Any) -> None:
                    # Uses something other than `self` the first arg to allow "self" as a settable attribute
                    values, fields_set, validation_error = validate_model(__pydantic_self__.__class__, data)
                    if validation_error:
            >           raise validation_error
            E           pydantic.v1.error_wrappers.ValidationError: 1 validation error for ChatOpenAI
            E           __root__
            E             AsyncClient.__init__() got an unexpected keyword argument 'proxies' (type=type_error)
            ../../../.cache/pypoetry/virtualenvs/biochatter-f6F-uYko-py3.11/lib/python3.11/site-packages/pydantic/v1/main.py:341: ValidationError
    """
    # Mock successful authentication
    mock_openai.return_value.models.list.return_value = ["gpt-3.5-turbo"]

    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        split_correction=False,
    )

    # Set API key (which will succeed)
    success = convo.set_api_key(api_key="fake_key")

    assert success

    # Verify both chat attributes are accessible
    assert convo.chat is not None
    assert convo.ca_chat is not None


def test_gpt_update_usage_stats():
    """Test the _update_usage_stats method in GptConversation."""
    # Arrange
    convo = GptConversation(
        model_name="gpt-3.5-turbo",
        prompts={},
        correct=False,
    )

    # Mock the usage_stats object
    mock_usage_stats = Mock()
    convo.usage_stats = mock_usage_stats
    convo.user = "community"  # Set user to enable stats tracking

    # Mock the update_token_usage callback
    mock_update_callback = Mock()
    convo._update_token_usage = mock_update_callback

    model = "gpt-3.5-turbo"
    token_usage = {
        "prompt_tokens": 50,
        "completion_tokens": 30,
        "total_tokens": 80,
        "non_numeric_field": "should be ignored",
        "nested_dict": {  # Should be ignored as it's a dictionary
            "sub_field": 100,
            "another_field": 200,
        },
        "another_field": "also ignored",
    }

    # Act
    convo._update_usage_stats(model, token_usage)

    # Assert
    # Verify increment was called with correct arguments for community stats
    # Only numeric values at the top level should be included
    mock_usage_stats.increment.assert_called_once_with(
        "usage:[date]:[user]",
        {
            "prompt_tokens:gpt-3.5-turbo": 50,
            "completion_tokens:gpt-3.5-turbo": 30,
            "total_tokens:gpt-3.5-turbo": 80,
        },
    )

    # Verify callback was called with complete token_usage including nested dict
    mock_update_callback.assert_called_once_with(
        "community",
        "gpt-3.5-turbo",
        token_usage,  # Full dictionary including nested values
    )


@patch("biochatter.llm_connect.ChatLiteLLM")
def test_get_litellm_object(mock_chatlite, dummy_api_key="dummy_key"):
    """
    Test that for a model name whether or not get_litellm_object
    calls ChatLiteLLM with the correct parameters.
    """
    uc = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    dummy_instance = MagicMock()
    mock_chatlite.return_value = dummy_instance

    result = uc.get_litellm_object(dummy_api_key)

    mock_chatlite.assert_called_with(
        temperature=0,
        openai_api_key=dummy_api_key,
        model_name="gpt-3.5-turbo"
    )
    assert result == dummy_instance
    
@patch("biochatter.llm_connect.ChatLiteLLM")
def test_get_litellm_object_unsupported_model(mock_chatlite, dummy_api_key="dummy_key"):
    """
    Test that an unsupported model name raises a ValueError.
    """
    uc = UnifiedConversation(model_name="unknown-model", prompts={})
    with pytest.raises(ValueError, match="Unsupported model: unknown-model"):
        uc.get_litellm_object(dummy_api_key)
    mock_chatlite.assert_not_called()
    
@patch.object(UnifiedConversation, "get_litellm_object")
def test_set_api_key_success(mock_get_llm, dummy_api_key="dummy_key"):
    """
    Test that set_api_key assigns chat and ca_chat correctly on success.
    """
    dummy_chat_instance = MagicMock()
    mock_get_llm.return_value = dummy_chat_instance

    uc = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    result = uc.set_api_key(dummy_api_key, user="test_user")

    assert result is True
    # The API key should be saved and both chat and ca_chat should be assigned.
    assert uc.api_key == dummy_api_key
    assert uc.chat == dummy_chat_instance
    assert uc.ca_chat == dummy_chat_instance
    assert uc.user == "test_user"

@patch.object(UnifiedConversation, "get_litellm_object")
def test_set_api_key_failure(mock_get_llm, dummy_api_key="dummy_key"):
    """
    Test that if get_litellm_object throws an exception, set_api_key returns False
    and does not initialize chat attributes.
    """
    mock_get_llm.side_effect = ValueError("Invalid API key")
    uc = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    result = uc.set_api_key(dummy_api_key, user="test_user")

    assert result is False
    with pytest.raises(AttributeError):
        _ = uc.chat
    with pytest.raises(AttributeError):
        _ = uc.ca_chat
    
def valid_response(token_usage):
    return {
        "generations": [
            [
                {
                    "message": {
                        "response_metadata": {
                            "token_usage": token_usage
                        }
                    },
                    "text": "dummy text"
                }
            ]
        ]
    }
  
def test_parse_llm_response_valid():
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    usage = {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
    response = valid_response(usage)
    result = conv.parse_llm_response(response)
    assert result == usage

def test_parse_llm_response_missing_generations():
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    # Missing 'generations' key
    response = {"not_generations": []}
    result = conv.parse_llm_response(response)
    assert result is None

def test_parse_llm_response_incomplete_structure():
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    # generations present but missing nested keys
    response = {"generations": [[{"no_message": {}}]]}
    result = conv.parse_llm_response(response)
    assert result is None

def test_parse_llm_response_none_input():
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    # Passing None should be caught and return None
    result = conv.parse_llm_response(None)
    assert result is None

def test_parse_llm_response_wrong_type():
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={})
    # Passing an integer instead of a dict; expect the conversion to fail and return None.
    result = conv.parse_llm_response(12345)
    assert result is None

def test_correct_response_ok():
    """Test _correct_response returns 'OK' when the generated response is OK."""
    # Arrange
    conv = UnifiedConversation(model_name="gpt-3.5-turbo", prompts={}, correct=True)
    conv.ca_messages = []  
    conv.ca_model_name = "gpt-3.5-turbo-correct"
    
    # Dummy generation returning "OK"
    dummy_generation = MagicMock()
    dummy_generation.text = "OK"
    dummy_response = MagicMock()
    dummy_response.generations = [[dummy_generation]]
    
    conv.ca_chat = MagicMock()
    conv.ca_chat.generate.return_value = dummy_response
    conv.parse_llm_response = MagicMock(return_value={"prompt_tokens": 5, "completion_tokens": 3})
    conv._update_usage_stats = MagicMock()
    
    # Act
    correction = conv._correct_response("Some response that needs no correction")
    
    # Assert
    assert correction == "OK"
    conv.ca_chat.generate.assert_called_once()
    conv._update_usage_stats.assert_called_once_with("gpt-3.5-turbo-correct", {"prompt_tokens": 5, "completion_tokens": 3})

MOCK_PROMPTS = {
    "primary_model_prompts": ["Test system prompt"],
    "correcting_agent_prompts": ["Test correcting agent prompt"],
    "rag_agent_prompts": ["Test RAG agent prompt", "Test RAG agent prompt with {statements}"],
    "tool_prompts": {"test_tool": "Test tool prompt with {df}"}
}

MOCK_MODEL_LIST = ["gpt-4", "gpt-3.5-turbo", "claude-2", "claude-instant-1"]

MOCK_MODELS_BY_PROVIDER = {
    "openai": ["gpt-4", "gpt-3.5-turbo"],
    "anthropic": ["claude-2", "claude-instant-1"]
}

MOCK_MODEL_COST = {
    "gpt-4": {"max_tokens": 8192, "input_cost_per_token": 0.00003, "output_cost_per_token": 0.00006},
    "gpt-3.5-turbo": {"max_tokens": 4096, "input_cost_per_token": 0.0000015, "output_cost_per_token": 0.000002},
    "claude-2": {"max_tokens": 100000, "input_cost_per_token": 0.00001102, "output_cost_per_token": 0.00003268}
}

# Setup and teardown fixtures
@pytest.fixture
def setup_mocks():
    """Setup all the mocks needed for the tests."""
    with patch('litellm.model_list', MOCK_MODEL_LIST), \
         patch('litellm.models_by_provider', MOCK_MODELS_BY_PROVIDER), \
         patch('litellm.model_cost', MOCK_MODEL_COST):
        yield

@pytest.fixture
def conversation(setup_mocks):
    """Create a mock UnifiedConversation instance."""
    from biochatter.llm_connect import UnifiedConversation

    conversation = UnifiedConversation(
        model_name="gpt-4",
        prompts=MOCK_PROMPTS,
        correct=True,
        split_correction=False,
        use_ragagent_selector=False,
        update_token_usage=None
    )
    
    conversation._chat = MagicMock()
    conversation._ca_chat = MagicMock()
    conversation.ca_model_name = "gpt-4"
    
    return conversation

def test_correct_response(conversation):
    """Test the _correct_response method."""
    # Arrange
    test_message = "This is a test message that needs correction."
    expected_correction = "OK"
    
    conversation.ca_messages = [
        SystemMessage(content="Test correcting agent prompt")
    ]
    
    mock_response = MagicMock()
    mock_response.generations = [[MagicMock(text=expected_correction)]]
    conversation.ca_chat.generate.return_value = mock_response
    
    conversation.parse_llm_response = MagicMock(return_value={"input_tokens": 10, "output_tokens": 5})
    
    conversation._update_usage_stats = MagicMock()
    
    result = conversation._correct_response(test_message)
    
    assert result == expected_correction
    conversation.ca_chat.generate.assert_called_once()
    conversation.parse_llm_response.assert_called_once_with(mock_response)
    conversation._update_usage_stats.assert_called_once_with(
        conversation.ca_model_name, 
        {"input_tokens": 10, "output_tokens": 5}
    )
    
    call_args = conversation.ca_chat.generate.call_args[0][0]
    assert len(call_args[0]) == 3  
    assert isinstance(call_args[0][0], SystemMessage)
    assert isinstance(call_args[0][1], HumanMessage)
    assert isinstance(call_args[0][2], SystemMessage)
    assert call_args[0][1].content == test_message

def test_get_model_max_tokens(conversation):
    """Test the get_model_max_tokens method."""
    model_name = "gpt-4"
    expected_max_tokens = 8192
    
    result = conversation.get_model_max_tokens(model_name)
    
    # Assert
    assert result == expected_max_tokens

def test_get_model_max_tokens_not_found(conversation):
    from litellm.exceptions import NotFoundError
    """Test the get_model_max_tokens method with a model that doesn't exist."""
    model_name = "nonexistent-model"
    
    conversation.get_model_info = MagicMock(side_effect=NotFoundError(
        message="Model information is not available.",
        model=model_name,
        llm_provider="Unknown"
    ))
    
    with pytest.raises(NotFoundError):
        conversation.get_model_max_tokens(model_name)

def test_get_model_max_tokens_missing_info(conversation):
    """Test the get_model_max_tokens method with a model that exists but missing max_tokens."""
    model_name = "gpt-4"
    
    conversation.get_model_info = MagicMock(return_value={
        "input_cost_per_token": 0.00003, 
        "output_cost_per_token": 0.00006
    })
    
    with pytest.raises(NotFoundError):
        conversation.get_model_max_tokens(model_name)

def test_get_model_info(conversation):
    """Test the get_model_info method."""
    model_name = "gpt-4"
    expected_info = {
        "max_tokens": 8192, 
        "input_cost_per_token": 0.00003, 
        "output_cost_per_token": 0.00006
    }
    
    result = conversation.get_model_info(model_name)
    
    assert result == expected_info

def test_get_model_info_not_found(conversation):
    """Test the get_model_info method with a model that doesn't exist."""
    model_name = "nonexistent-model"
    
    with pytest.raises(NotFoundError):
        conversation.get_model_info(model_name)

def test_get_all_model_info(conversation):
    """Test the get_all_model_info method."""
    expected_info = MOCK_MODEL_COST
    
    result = conversation.get_all_model_info()
    
    assert result == expected_info

def test_get_models_by_provider(conversation):
    """Test the get_models_by_provider method."""
    expected_models = MOCK_MODELS_BY_PROVIDER
    
    result = conversation.get_models_by_provider()
    
    assert result == expected_models

def test_get_all_model_list(conversation):
    """Test the get_all_model_list method."""
    expected_models = MOCK_MODEL_LIST
    
    result = conversation.get_all_model_list()
    
    assert result == expected_models
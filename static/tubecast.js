var isAlpha = function( strIn ){
	var re_alpha = /[^a-zA-Z0-9_-]/;
	return !re_alpha.test( strIn );
}

var getParameterByName = function ( name, urlString ) {
    name = name.replace(/[\[]/, "\\[").replace(/[\]]/, "\\]");
    var regex = new RegExp("[\\?&]" + name + "=([^&#]*)"),
        results = regex.exec( urlString );
    return results === null ? "" : decodeURIComponent(results[1].replace(/\+/g, " "));
}

var idFromInput = function(){
	input = $("#urlBox").val();

	console.log( input );

	if( isAlpha(input) ) {
		return input;
	}
	else {
		var id = getParameterByName( "list", input );
		return id;
	}
	return null;
}


$(function(){

	var feedURL = window.location.host + "/feed/";

	$("#btniTunes").click( function(e){
		e.preventDefault();
		window.location = "itpc://" + feedURL + idFromInput();
	});

	$("#btnFeed").click( function(e){
		e.preventDefault();
		window.location = "http://" + feedURL + idFromInput();
	});

});
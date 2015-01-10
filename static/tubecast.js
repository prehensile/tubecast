var isAlpha = function( strIn ){
	var re_alpha = /[^a-zA-Z0-9_-]/;
	return !re_alpha.test( strIn );
}

var getParameterByName = function ( name, urlString ) {
    name = name.replace(/[\[]/, "\\[").replace(/[\]]/, "\\]");
    var regex = new RegExp("[\\?&]" + name + "=([^&#]*)"),
        results = regex.exec( urlString );
    return results === null ? null : decodeURIComponent(results[1].replace(/\+/g, " "));
}

var idFromInput = function(){
	input = $("#urlBox").val();
	var id = null;
	if( isAlpha(input) ) {
		return input;
	}
	else {
		id = getParameterByName( "list", input );
	}
	return id;
}

var redirectToFeed = function( protocol ){
	var feedURL = window.location.host + "/feed/";
	var id = idFromInput();
	if( id ) {
		window.location = protocol + "://" + feedURL + id;
	} else {
		$("#formPlaylist").toggleClass( "has-error", true );
	}
}

$(function(){
	$("#btniTunes").click( function(e){
		e.preventDefault();
		redirectToFeed( "itpc" );
	});
	$("#btnFeed").click( function(e){
		e.preventDefault();
		redirectToFeed( "http" );
	});
	$("#urlBox").focusin( function(e){
		$("#formPlaylist").toggleClass( "has-error", false );
	});
});